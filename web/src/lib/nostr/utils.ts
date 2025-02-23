import {getEventHash, nip05, nip19, Kind, getPublicKey} from "nostr-tools";
import { NostrPublicKey, NostrKeySource } from "$lib/stores";
import type { User } from "$lib/types/user";

export const pmChannelNostrRoomId = import.meta.env.VITE_NOSTR_MARKET_SQUARE_CHANNEL_ID;

export const relayUrlList = [
    // Amethyst relays
    "wss://relay.damus.io",
    "wss://relay.nostr.bg",
    "wss://nostr.mom",
    "wss://nos.lol",
    "wss://nostr.bitcoiner.social",
    "wss://nostr-pub.wellorder.net",
    "wss://nostr.wine",
    "wss://eden.nostr.land",
    "wss://relay.orangepill.dev",
    "wss://no.str.cr",
    "wss://puravida.nostr.land",
    "wss://relay.nostr.com.au",
    "wss://nostr.inosta.cc",
];

export const pmMasterPublicKey = 'df476caf4888bf5d99c6a710ea6ae943d3e693d29cdc75c4eff1cfb634839bb8';
export const localStorageNostrPreferPMId = 'nostr-prefer-pm-identity';

export function hasExtension() {
    return !!(window as any).nostr;
}

export async function getPreferredPublicKey(generatedNostrPrivateKey: string | null) {
    if ((!hasExtension() || localStorage.getItem(localStorageNostrPreferPMId) !== null) && generatedNostrPrivateKey !== null) {
        // using PM-generated identity
        return getPublicKey(generatedNostrPrivateKey);
    } else {
        return await (window as any).nostr.getPublicKey();
    }
}

export async function wait(milliseconds) {
    await new Promise(resolve => setTimeout(resolve, milliseconds));
}

export const formatTimestamp = ts => {
    const today = new Date().setHours(0, 0, 0, 0);
    const thatDay = new Date(ts * 1000).setHours(0, 0, 0, 0);

    let format;

    if (today === thatDay) {
        format = {
            timeStyle: 'short',
        };
    } else {
       format = {
            dateStyle: 'medium',
            timeStyle: 'short',
        };
    }

    const formatter = new Intl.DateTimeFormat('en-US', format);

    return formatter.format(new Date(ts * 1000));
}

export function getChannelIdForStallOwner(user) {
    let stallName = `Plebeian Market Stall ${user.identity} (${import.meta.env.MODE})`;

    console.debug('   ** Nostr: Stall channel name: ', stallName);

    // Please, don't change this, since we're faking channel
    // creation, so we need the same channel ID every time
    let created_at = 1672837282;

    let event = {
        kind: Kind.ChannelCreation,
        pubkey: pmMasterPublicKey,
        created_at: created_at,
        content: '{"name": "' + stallName + '", "about": "Plebeian Market Stall Square."}',
        tags: [],
    }

    return getEventHash(event);
}

export async function queryNip05(fullname) {
    let profile;

    try {
        profile = await nip05.queryProfile(fullname);
    } catch (e) {
        console.debug("   ** Nostr: Problem while trying to verify nip05 (" + fullname + "):", e);
        return false;
    }

    if (profile && profile.pubkey) {
        return profile.pubkey;
    }

    return false;
}

export function filterTags(tagsArray, tagToFilter) {
    return tagsArray.filter(t => {
        return t[0] === tagToFilter;
    });
}

export function findMarkerInTags(tags, tagType, marker) {
    let found = false;

    tags.forEach(tag => {
        if (tag[0] === tagType && tag[3] === marker) {
            found = true;
        }
    })

    return found;
}

export function getEventReplyingTo(event) {
    if (event.kind !== 1) {
        return undefined;
    }
    const replyTags = event.tags.filter((tag) => tag[0] === 'e');
    if (replyTags.length === 1) {
        return replyTags[0][1];
    }
    const replyTag = event.tags.find((tag) => tag[0] === 'e' && tag[3] === 'reply');
    if (replyTag) {
        return replyTag[1];
    }
    if (replyTags.length > 1) {
        return replyTags[1][1];
    }
    return undefined;
}

export function getBestRelay() {
    // let relays = getPerson(pubkey)?.relays

    return relayUrlList[0];
}

export async function setPublicKey(user: User | null) {
    if (!hasExtension() || (hasExtension() && localStorage.getItem(localStorageNostrPreferPMId) !== null)) {
        // Using PM Nostr identity
        if (!user) {
            NostrPublicKey.set({source: NostrKeySource.PlebeianMarketUser, key: null});
            return false;
        }

        let userPrivateKey = user.nostr_private_key;
        if (userPrivateKey === null) {
            NostrPublicKey.set({source: NostrKeySource.PlebeianMarketUser, key: null});
            return false;
        }

        let publicKey = getPublicKey(userPrivateKey);

        NostrPublicKey.set({source: NostrKeySource.PlebeianMarketUser, key: publicKey});
    } else {
        // Using Nostr extension identity
        try {
            NostrPublicKey.set({source: NostrKeySource.Extension, key: await (window as any).nostr.getPublicKey()});
        } catch (error) {
            NostrPublicKey.set({source: NostrKeySource.Extension, key: null});
            return false;
        }
    }

    return true;
}

export function getKeyFromKeyOrNpub(key: string) {
    if (key.toLowerCase().startsWith("npub")) {
        let decoded = nip19.decode(key);
        if (typeof decoded.data !== 'string') {
            return null;
        }
        return decoded.data;
    }

    return key;
}