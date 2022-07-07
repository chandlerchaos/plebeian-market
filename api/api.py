from datetime import datetime, timedelta
from io import BytesIO
import os
import secrets

import ecdsa
from ecdsa.keys import BadSignatureError
from flask import Blueprint, jsonify, request
import jwt
import lnurl
import pyqrcode
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.functions import func

from extensions import db
import models as m
from main import app, get_lnd_client, get_s3, get_twitter
from main import get_token_from_request, get_user_from_token, user_required

api_blueprint = Blueprint('api', __name__)

@api_blueprint.route('/api/healthcheck', methods=['GET'])
def healthcheck(): # TODO: I don't really like this, for some reason, but it is used in "dev" mode by docker-compose
    return jsonify({'success': True})

# TODO: It would be nice to extract this into a separate Python package that can be used by any (Flask?) project.
@api_blueprint.route('/api/login', methods=['GET'])
def login():
    """
    Log in with a Lightning wallet.
    """

    if 'k1' not in request.args:
        # first request to /login => we return a challenge (k1) and a QR code
        k1 = secrets.token_hex(32)

        db.session.add(m.LnAuth(k1=k1))
        db.session.commit()

        url = app.config['BASE_URL'] + f"/api/login?tag=login&k1={k1}"
        ln_url = lnurl.encode(url).bech32
        qr = BytesIO()
        pyqrcode.create(ln_url).svg(qr, omithw=True, scale=4)

        return jsonify({'k1': k1, 'lnurl': str(ln_url), 'qr': qr.getvalue().decode('utf-8')})

    lnauth = m.LnAuth.query.filter_by(k1=request.args['k1']).first()

    if not lnauth or lnauth.created_at < datetime.utcnow() - timedelta(minutes=m.LnAuth.EXPIRE_MINUTES):
        return jsonify({'message': "Verification failed."}), 400

    if 'key' in request.args and 'sig' in request.args:
        # request made by the Lightning wallet, includes a key and a signature

        if lnauth.key and request.args['key'] != lnauth.key:
            # lnauth should not have a "key" here, unless the user scanned the QR code already
            # but then the key in the request should match the key we saved on the previous scan
            app.logger.warning(f"Dubious request with a key {request.args['key']} different from the existing key for k1 {lnauth.k1}.")
            return jsonify({'message': "Verification failed."}), 400
        if not lnauth.key:
            try:
                k1_bytes, key_bytes, sig_bytes = map(lambda k: bytes.fromhex(request.args[k]), ['k1', 'key', 'sig'])
            except ValueError:
                return jsonify({'message': "Invalid parameter."}), 400

            vk = ecdsa.VerifyingKey.from_string(key_bytes, curve=ecdsa.SECP256k1)
            try:
                vk.verify_digest(sig_bytes, k1_bytes, sigdecode=ecdsa.util.sigdecode_der)
            except BadSignatureError:
                return jsonify({'message': "Verification failed."}), 400

            lnauth.key = request.args['key']

            db.session.commit()

        return jsonify({})

    if not lnauth.key:
        # this is the browser continuously checking whether log in happened by passing in the challenge (k1)
        return jsonify({'success': False})

    # we are now logged in, so find the user, delete the lnauth and return the JWT token

    user = m.User.query.filter_by(key=lnauth.key).first()

    if not user:
        user = m.User(key=lnauth.key)
        db.session.add(user)

    db.session.delete(lnauth)
    db.session.commit()

    token = jwt.encode({'user_key': user.key, 'exp': datetime.utcnow() + timedelta(hours=24)}, app.config['SECRET_KEY'], "HS256")

    return jsonify({'success': True, 'token': token, 'user': user.to_dict()})

@api_blueprint.route('/api/users/me', methods=['GET', 'POST'])
@user_required
def me(user):
    if request.method == 'GET':
        return jsonify({'user': user.to_dict()})
    else:
        if 'nym' in request.json:
            return jsonify({'message': "Can't edit nym."}), 400 # yet, I guess...
        if 'twitter_username' in request.json:
            clean_username = request.json['twitter_username'] or ""
            if clean_username.startswith("@"):
                clean_username = clean_username[1:]
            if not clean_username:
                return jsonify({'message': "Invalid Twitter username!"}), 400
            if clean_username != user.twitter_username:
                user.twitter_username = clean_username

                twitter = get_twitter()

                twitter_user = twitter.get_user(user.twitter_username)
                if not twitter_user:
                    return jsonify({'message': "Twitter profile not found!"}), 400

                user.twitter_profile_image_url = twitter_user['profile_image_url']
                if not user.fetch_twitter_profile_image(get_s3()):
                    return jsonify({'message': "Error fetching profile picture!"}), 400

                user.twitter_username_verified = False

                plebeian_twitter_user = twitter.get_user(app.config['TWITTER_USER'])

                user.twitter_username_verification_tweet_id = plebeian_twitter_user['pinned_tweet_id']

        if 'contribution_percent' in request.json:
            user.contribution_percent = request.json['contribution_percent']
        try:
            db.session.commit()
        except IntegrityError:
            return jsonify({'message': "Somebody already registered this Twitter username!"}), 400
        return jsonify({'user': user.to_dict()})

@api_blueprint.route('/api/users/me/verify-twitter', methods=['PUT'])
@user_required
def verify_twitter(user):
    liking_usernames = get_twitter().get_tweet_likes(user.twitter_username_verification_tweet_id)
    if not user.twitter_username in liking_usernames:
        return jsonify({'message': "Please like the tweet to verify your username."}), 400
    else:
        user.twitter_username_verified = True
        db.session.commit()
        return jsonify({})

@api_blueprint.route('/api/users/me/notifications', methods=['GET', 'PUT'])
@user_required
def user_notifications(user):
    existing_notifications = {
        n.notification_type: n for n in m.UserNotification.query.filter_by(user_id=user.id).all()
    }
    if request.method == 'GET':
        notifications = list(existing_notifications.values())
        for notification_type in set(m.NOTIFICATION_TYPES.keys()) - set(existing_notifications.keys()):
            notifications.append(m.UserNotification(notification_type=notification_type, action=m.NOTIFICATION_TYPES[notification_type]['default_action']))
        return jsonify({'notifications': [n.to_dict() for n in notifications]})
    elif request.method == 'PUT':
        for notification in request.json['notifications']:
            if notification['notification_type'] not in existing_notifications:
                new_notification = m.UserNotification(user_id=user.id, notification_type=notification['notification_type'], action=notification['action'])
                db.session.add(new_notification)
            else:
                existing_notifications[notification['notification_type']].action = notification['action']
        db.session.commit()
        return jsonify({})

@api_blueprint.route('/api/auctions', methods=['GET', 'POST'])
@user_required
def auctions(user):
    if request.method == 'GET':
        auctions = [a.to_dict(for_user=user.id) for a in user.auctions]
        return jsonify({'auctions': auctions})
    else:
        # TODO: prevent seller from creating too many auctions?

        for k in ['title', 'description', 'duration_hours', 'starting_bid', 'reserve_bid']:
            if k not in request.json:
                return jsonify({'message': f"Missing key: {k}."}), 400

        try:
            validated = m.Auction.validate_dict(request.json)
        except m.ValidationError as e:
            return jsonify({'message': e.message}), 400

        auction_count = db.session.query(func.count(m.Auction.id).label('count')).first().count
        key = m.Auction.generate_key(auction_count)
        auction = m.Auction(seller=user, key=key, **validated)
        db.session.add(auction)
        db.session.commit()

        return jsonify({'auction': auction.to_dict(for_user=user.id)})

@api_blueprint.route('/api/auctions/featured', methods=['GET'])
def featured_auctions():
    auctions = m.Auction.query.filter(
        (m.Auction.is_featured == True)
        | ((m.Auction.is_featured == None)
         & (m.Auction.start_date <= datetime.utcnow())
         & (m.Auction.end_date >= datetime.utcnow()))
    ).all()
    return jsonify({'auctions': [a.to_dict() for a in auctions]})

@api_blueprint.route('/api/auctions/<string:key>', methods=['GET', 'PUT', 'DELETE'])
def auction(key):
    user = get_user_from_token(get_token_from_request())
    auction = m.Auction.query.filter_by(key=key).first()
    if not auction:
        return jsonify({'message': "Not found."}), 404

    if request.method == 'GET':
        if auction.ended:
            if auction.winning_bid_id is None and auction.contribution_payment_request is None:
                # auction ended, but no winning bid has been picked
                # => ask the user with the top bid to send the contribution
                if auction.reserve_bid_reached:
                    top_bid = auction.get_top_bid()
                    auction.contribution_amount = int(auction.seller.contribution_percent / 100 * top_bid.amount)
                    if auction.contribution_amount < app.config['MINIMUM_CONTRIBUTION_AMOUNT']:
                        auction.contribution_amount = 0 # probably not worth the fees, at least in the next few years

                        # settle the contribution and pick the winner right away
                        auction.contribution_requested_at = auction.contribution_settled_at = datetime.utcnow()
                        auction.winning_bid_id = top_bid.id
                    else:
                        response = get_lnd_client().add_invoice(value=auction.contribution_amount, expiry=app.config['LND_CONTRIBUTION_INVOICE_EXPIRY'])
                        auction.contribution_payment_request = response.payment_request
                        auction.contribution_requested_at = datetime.utcnow()
                    db.session.commit()
        return jsonify({'auction': auction.to_dict(for_user=(user.id if user else None))})
    else:
        is_changing_featured_state = request.method == 'PUT' and 'is_featured' in set(request.json.keys())
        is_changing_featured_state_only = request.method == 'PUT' and set(request.json.keys()) == {'is_featured'}

        if is_changing_featured_state and not is_changing_featured_state_only:
            return jsonify({'message': "When changing is_featured, nothing else can be changed in the same request."}), 400

        if not user:
            return jsonify({'message': "Unauthorized"}), 401
        if is_changing_featured_state and not user.is_moderator:
            return jsonify({'message': "Unauthorized"}), 401
        if user.id != auction.seller_id and not is_changing_featured_state:
            return jsonify({'message': "Unauthorized"}), 401

        if request.method == 'PUT':
            if auction.started and not is_changing_featured_state_only:
                return jsonify({'message': "Cannot edit an auction once started."}), 403

            try:
                validated = m.Auction.validate_dict(request.json)
            except m.ValidationError as e:
                return jsonify({'message': e.message}), 400

            for k, v in validated.items():
                setattr(auction, k, v)

            db.session.commit()

            return jsonify({})
        elif request.method == 'DELETE':
            # TODO: should we allow deletion of a started auction?
            db.session.delete(auction)
            db.session.commit()

            return jsonify({})

@api_blueprint.route('/api/auctions/<string:key>/follow', methods=['PUT'])
@user_required
def follow_auction(user, key):
    auction = m.Auction.query.filter_by(key=key).first()
    if not auction:
        return jsonify({'message': "Not found."}), 404

    follow = bool(request.json['follow'])

    user_auction = m.UserAuction.query.filter_by(user_id=user.id, auction_id=auction.id).one_or_none()
    if user_auction is None:
        user_auction = m.UserAuction(user_id=user.id, auction_id=auction.id, following=follow)
        db.session.add(user_auction)
    else:
        user_auction.following = follow
    db.session.commit()

    return jsonify({})

@api_blueprint.route('/api/auctions/<string:key>/start-twitter', methods=['PUT'])
@user_required
def start_twitter(user, key):
    auction = m.Auction.query.filter_by(key=key).first()
    if not auction:
        return jsonify({'message': "Not found."}), 404
    if auction.seller_id != user.id:
        return jsonify({'message': "Unauthorized"}), 401

    twitter = get_twitter()
    twitter_user = twitter.get_user(user.twitter_username)
    if not twitter_user:
        return jsonify({'message': "Twitter profile not found!"}), 400

    user.twitter_profile_image_url = twitter_user['profile_image_url']
    if not user.fetch_twitter_profile_image(get_s3()):
        return jsonify({'message': "Error fetching profile picture!"}), 400

    tweets = twitter.get_auction_tweets(twitter_user['id'])
    tweet = None
    for t in sorted(tweets, key=lambda t: t['created_at'], reverse=True):
        # we basically pick the last tweet that matches the auction
        if t['auction_key'] == auction.key:
            tweet = t
            break

    if not tweet:
        return jsonify({'message': "Tweet not found."}), 400

    if not tweet['photos']:
        return jsonify({'message': "Tweet does not have any attached pictures."}), 400

    user.twitter_username_verified = True
    auction.twitter_id = tweet['id']
    auction.start_date = datetime.utcnow()
    auction.end_date = auction.start_date + timedelta(hours=auction.duration_hours)

    m.Media.query.filter_by(auction_id=auction.id).delete()

    s3 = get_s3()
    for i, photo in enumerate(tweet['photos'], 1):
        media = m.Media(auction_id=auction.id, twitter_media_key=photo['media_key'], url=photo['url'])
        if not media.fetch(s3, f"auction_{auction.key}_media_{i}"):
            return jsonify({'message': "Error fetching picture!"}), 400
        db.session.add(media)

    db.session.commit()

    return jsonify({})

@api_blueprint.route('/api/auctions/<string:key>/bids', methods=['POST'])
@user_required
def bids(user, key):
    auction = m.Auction.query.filter_by(key=key).first()
    if not auction:
        return jsonify({'message': "Not found."}), 404

    if not auction.started or auction.ended:
        return jsonify({'message': "Auction not running."}), 403

    amount = int(request.json['amount'])

    top_bid = auction.get_top_bid()
    if top_bid and amount <= top_bid.amount:
        return jsonify({'message': f"The top bid is currently {top_bid.amount}. Your bid needs to be higher!"}), 400
    elif amount <= auction.starting_bid:
        return jsonify({'message': f"Your bid needs to be higher than {auction.starting_bid}, the starting bid."}), 400

    response = get_lnd_client().add_invoice(value=app.config['LND_BID_INVOICE_AMOUNT'], expiry=app.config['LND_BID_INVOICE_EXPIRY'])

    payment_request = response.payment_request

    bid = m.Bid(auction=auction, buyer=user, amount=amount, payment_request=payment_request)
    db.session.add(bid)
    db.session.commit()

    qr = BytesIO()
    pyqrcode.create(payment_request).svg(qr, omithw=True, scale=4)

    return jsonify({'payment_request': payment_request, 'qr': qr.getvalue().decode('utf-8')})
