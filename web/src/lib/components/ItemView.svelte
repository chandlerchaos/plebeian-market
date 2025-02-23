<script lang="ts">
    import { onDestroy, onMount } from "svelte";
    import SvelteMarkdown from 'svelte-markdown';
    import { MetaTags } from 'svelte-meta-tags';
    import { ErrorHandler, getItem, putAuctionFollow, type ILoader } from "$lib/services/api";
    import { Error, Info, token, user, AuthRequired } from "$lib/stores";
    import { Category, type Item } from "$lib/types/item";
    import { Auction } from "$lib/types/auction";
    import { Listing } from "$lib/types/listing";
    import { SaleState, type Sale } from "$lib/types/sale";
    import AmountFormatter from "$lib/components/AmountFormatter.svelte";
    import Avatar from "$lib/components/Avatar.svelte";
    import BidButton from "$lib/components/BidButton.svelte";
    import BidList from "$lib/components/BidList.svelte";
    import BuyButton from "$lib/components/BuyButton.svelte";
    import Countdown from "$lib/components/Countdown.svelte";
    import Gallery from "$lib/components/Gallery.svelte";
    import SaleFlow from "$lib/components/SaleFlow.svelte";
    import { page } from "$app/stores";
    import { getBaseUrl, getShortTitle, getShortDescription } from "$lib/utils";
    import TweetButton from "$lib/components/TweetButton.svelte";
    import NostrButton from "$lib/components/nostr/Button.svelte";
    import ErrorBox from "$lib/components/notifications/ErrorBox.svelte";

    export let loader: ILoader;
    export let itemKey = null;
    export let serverLoadedItem: Auction | Listing;

    let bidButton: BidButton;

    let sale: Sale | null = null;

    let item: Item | null = null;
    let bidCount = 0;
    let amount: number | null = null;
    let firstUpdate = true;

    let tweetURL: string | null = null;

    function refreshItem() {
        getItem(loader, $token, itemKey,
            i => {
                item = i;
                if (!item) {
                    return;
                }

                if (item instanceof Auction) {
                    if (bidButton && bidButton.bidConfirmed && bidButton.waitingBidSettlement && bidButton.waitingBadgeSale && bidButton.resetBid) { // TODO: why are these checks needed? Typescript trying to be smart? Svelte acting stupid? Can we get rid of them?
                        for (const bid of item.bids) {
                            if (bid.payment_request !== null) {
                                // NB: payment_request being set on the Bid means this is *my* bid, which has been confirmed
                                bidButton.bidConfirmed(bid.payment_request);
                            }
                            if (amount && amount <= bid.amount && (bidButton.waitingBidSettlement() || bidButton.waitingBadgeSale())) {
                                Error.set("A higher bid just came in.");
                                bidButton.resetBid();
                            }
                        }
                    }

                    if ((!amount && firstUpdate) || item.bids.length != bidCount) {
                        amount = item.nextBid();
                        firstUpdate = false;
                    }
                    bidCount = item.bids.length;
                    if (finalCountdown && finalCountdown.isLastMinute()) {
                        document.title = `LAST MINUTE - ${item.title} | Plebeian Market`;
                    } else {
                        document.title = `${item.title} | Plebeian Market`;
                    }
                    if (item.has_winner !== null) {
                        document.title = `Ended - ${item.title} | Plebeian Market`;
                        console.log("Auction ended!");
                        // maybe we should eventually stopRefresh() here, but is seems risky for now, at least while still testing
                    }
                } else if (item instanceof Listing) {
                    document.title = `${item.title} | Plebeian Market`;
                }

                var last_sale = item.sales.slice(-1).pop();
                if (last_sale) {
                    sale = last_sale;
                }

                tweetURL = 'https://twitter.com/intent/tweet?url=' + encodeURIComponent(getBaseUrl() + 'auctions/' + item?.key) + '&text=' + item?.title;
            },
            new ErrorHandler(false));
    }

    function followAuction() {
        if (item instanceof Auction) {
            let auction = item;
            if (auction) {
                auction.following = !auction.following;
                putAuctionFollow($token, auction.key, auction.following,
                    message => {
                        Info.set(message);
                    });
            }
        }
    }

    let interval: ReturnType<typeof setInterval> | undefined;

    let finalCountdown;

    onMount(async () => {
        refreshItem();
        interval = setInterval(refreshItem, 1000);
    });

    function stopRefresh() {
        if (interval) {
            clearInterval(interval);
            interval = undefined;
        }
    }

    onDestroy(stopRefresh);
</script>

{#if serverLoadedItem}
<MetaTags
    title={getShortTitle(serverLoadedItem.title)}
    description={getShortDescription(serverLoadedItem.description)}
    openGraph={{
        site_name: import.meta.env.VITE_SITE_NAME,
        type: 'website',
        url: $page.url.href,
        title: getShortTitle(serverLoadedItem.title),
        description: getShortDescription(serverLoadedItem.description),
        images: [{ url: serverLoadedItem.media.length ? serverLoadedItem.media[0].url : getBaseUrl() + "images/logo.png" }],
    }}
    twitter={{
        site: import.meta.env.VITE_TWITTER_USER,
        handle: import.meta.env.VITE_TWITTER_USER,
        cardType: "summary_large_image",
        image: serverLoadedItem.media.length ? serverLoadedItem.media[0].url : getBaseUrl() + "images/logo.png",
        imageAlt: getShortTitle(serverLoadedItem.title)
    }}
/>
{/if}

{#if item}
    <div class="lg:w-2/3 mx-auto p-2">
        {#if $user && item.is_mine && !item.started}
            <div class="mt-12 lg:w-2/3 mx-auto">
                <ErrorBox>
                    <span>Your sale is not active. Please go to <a class="link" href="/stall/{$user.nym}#item-{item.key}">My stall</a> and click Publish!</span>
                </ErrorBox>
            </div>
        {/if}
        {#if !item.is_mine}
            {#if sale && sale.state === SaleState.EXPIRED}
                <ErrorBox>
                    <span>Sale expired. The transaction was not confirmed in time.</span>
                </ErrorBox>
            {:else if sale && sale.state === SaleState.TX_CONFIRMED}
                <div class="alert alert-success shadow-lg">
                    <div>
                        <svg xmlns="http://www.w3.org/2000/svg" class="stroke-current flex-shrink-0 h-6 w-6" fill="none" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <span>
                            Your payment has been confirmed!
                        </span>
                    </div>
                </div>
            {/if}
        {/if}

        <div class="grid">
            <div class="py-6">
                <h2 class="lg:text-6xl text-3xl lg:w-1/2 mx-auto font-black text-center my-2 rounded-t py-1.5">{item.title}</h2>
                <!-- CONTENT -->
                <div class="grid lg:grid-cols-3 mt-6 mb-2">
                  <!-- LEFT  -->
                  <div class="lg:sticky top-24">
                      <!-- IMAGES -->
                      <div class="w-full">
                          <Gallery photos={item.media} />
                      </div>

                      <!-- DETAILS -->
                      <div>
                          <div class="">
                              <div class="markdown-container mt-12 lg:w-2/3">
                                  <SvelteMarkdown source={item.description} />
                              </div>

                              {#if item.category !== Category.Time}
                                  <p class="mt-4 ml-2">NOTE: Please allow for post and packaging.</p>
                              {/if}

                              {#if item.shipping_from}
                                  <h3 class="text-1xl md:text-3xl mt-4 ml-2">Shipping from {item.shipping_from}</h3>
                              {/if}

                              {#if item.shipping_domestic_usd}
                                  <p class="mt-4 ml-2">Shipping (domestic): ~<AmountFormatter usdAmount={item.shipping_domestic_usd} /></p>
                              {/if}
                              {#if item.shipping_worldwide_usd}
                                  <p class="mt-4 ml-2">Shipping (worldwide): ~<AmountFormatter usdAmount={item.shipping_worldwide_usd} /></p>
                              {/if}
                              <p class="mt-4 ml-2">
                                  {#if item instanceof Auction}
                                      {#if item.start_date && item.end_date}
                                          {#if item.ended}
                                              Auction ended.
                                          {/if}
                                      {:else if !item.is_mine}
                                          Keep calm, prepare your wallet and wait for the seller to start this auction.
                                      {/if}
                                  {/if}
                              </p>
                          </div>

                          <div class="grid">
                              {#if item.campaign_name !== null}
                                  <div class="badge badge-primary mb-4"><a href="/campaigns/{item.campaign_key}">{item.campaign_name} campaign</a></div>
                              {/if}
                              <div class="grid place-content-start">
                                  <Avatar account={item.seller} />
                              </div>

                              {#if item instanceof Auction}
                                  <div class="form-control flex place-items-start">
                                      <label class="label cursor-pointer text-left">
                                          <span class="label-text mr-4">Follow auction</span>
                                          <input type="checkbox" on:click|preventDefault={followAuction} bind:checked={item.following} class="checkbox checkbox-primary checkbox-lg" />
                                      </label>
                                  </div>
                              {/if}
                          </div>
                      </div>
                  </div>

                  <!-- BIDS -->
                  <div class="lg:col-span-2 p-5 border w-full border-gray-700/40 rounded">
                    {#if item.ended}
                        {#if item instanceof Auction}
                            <h3 class="text-2xl text-center my-2">
                                Auction ended
                            </h3>
                            {#if item.is_mine}
                                <div class="my-8 flex gap-2 items-center justify-center">
                                    {#if item.has_winner && item.winner}
                                        <span>The winner is</span>
                                        <Avatar account={item.winner} inline={true} />
                                    {:else}
                                        <span>The auction doesn't have a winner.</span>
                                    {/if}
                                </div>
                                {#if sale}
                                    {#if sale.state === SaleState.TX_DETECTED || sale.state === SaleState.TX_CONFIRMED}
                                        <p class="my-4 text-center w-full">Please contact the winner using <a class="link" href="https://twitter.com/direct_messages/create/{sale.buyer.twitterUsername}" target="_blank" rel="noreferrer">Twitter DM</a> to discuss further.</p>
                                        <div class="alert shadow-lg my-4" class:alert-warning={sale.state === SaleState.TX_DETECTED} class:alert-success={sale.state === SaleState.TX_CONFIRMED}>
                                            <div>
                                                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" class="stroke-current flex-shrink-0 w-6 h-6"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                                                <span>
                                                    TxID: <a class="link break-all" target="_blank" href="https://mempool.space/tx/{sale.txid}" rel="noreferrer">{sale.txid}</a>
                                                </span>
                                            </div>
                                        </div>
                                        {#if item.campaign_name !== null}
                                            <div class="text-center text-2xl my-8">
                                                <p>Note: all the money goes from the buyer <strong>directly to</strong></p>
                                                <div class="badge badge-primary my-4"><a href="/campaigns/{item.campaign_key}">{item.campaign_name} campaign</a></div>
                                            </div>
                                        {/if}
                                    {:else if sale.state === SaleState.EXPIRED}
                                        <div class="my-4">
                                            <ErrorBox>
                                                <span>
                                                    {#if sale.txid !== null}
                                                        Unfortunately, the transaction did not confirm in time!
                                                        <br />
                                                        TxID: <a class="link break-all" target="_blank" href="https://mempool.space/tx/{sale.txid}" rel="noreferrer">{sale.txid}</a>
                                                    {:else}
                                                        We didn't find a corresponding transaction!
                                                    {/if}
                                                </span>
                                            </ErrorBox>
                                        </div>
                                    {:else}
                                        <p class="text-center text-2xl my-4">Waiting for the payment...</p>
                                        <p class="text-center text-xl my-6">
                                            This screen will update. As soon as the payment is detected, you'll receive instructions on what to do on this screen and in your Twitter DM. You can also close this screen and come back to it later.
                                        </p>
                                    {/if}
                                {/if}
                            {/if}
                        {/if}
                    {/if}
                    {#if !item.is_mine && sale && sale.state !== SaleState.EXPIRED}
                        <SaleFlow bind:item={item} bind:sale={sale} />
                    {/if}
                    {#if !item.ended}
                        {#if $token && $user}
                            {#if !item.is_mine}
                                {#if $user.nym !== null && item.started}
                                    {#if !item.ended}
                                        {#if item instanceof Auction}
                                            {#if !item.bids.length}
                                                <p class="text-3xl text-center pt-24">Starting bid is <AmountFormatter satsAmount={item.starting_bid} />.</p>
                                                <p class="text-2xl text-center pt-2">Be the first to bid!</p>
                                                <p class="text-center pt-12 mb-4">Place your bid below</p>
                                            {/if}
                                            <div class="flex justify-center items-center">
                                                <BidButton auction={item} bind:amount bind:this={bidButton} />
                                            </div>
                                        {:else if item instanceof Listing}
                                            {#if !sale || sale.state === SaleState.TX_CONFIRMED || sale.state === SaleState.EXPIRED}
                                                <div class="mt-8 flex justify-center items-center">
                                                    <BuyButton {item} onSale={(s) => {sale = s;}} />
                                                </div>
                                            {/if}
                                        {/if}
                                    {/if}
                                {/if}
                            {:else}
                                {#if item.started}
                                    <p class="text-4xl text-center pt-10">
                                        {#if item instanceof Auction}
                                            Your auction is live! <br />
                                        {:else if item instanceof Listing}
                                            Your listing is live! <br />
                                            <br />
                                            Note: You can still edit it, by going to <a class="link" href="/stall/{$user.nym}">My stall</a>!
                                        {/if}
                                    </p>
                                    <div class="text-xl text-center mt-10 mb-1">
                                        Now let your audience know!
                                        &nbsp;
                                        <TweetButton tweetURL={tweetURL} />
                                        <NostrButton pmURL={window.location.href} />
                                    </div>
                                {/if}
                            {/if}
                        {:else}
                            {#if item instanceof Auction && !item.bids.length}
                                <p class="text-center pt-24">Login to place a bid!</p>
                            {:else if item instanceof Listing}
                                <p class="text-center pt-24">Login to buy this item for <AmountFormatter usdAmount={item.price_usd} />!</p>
                            {/if}

                            <div class="w-full my-8 grid place-items-center">
                                <p class="btn btn-primary font-bold text-center" on:click={() => AuthRequired.set(true)} on:keypress={() => AuthRequired.set(true)}>Login</p>
                            </div>
                        {/if}
                    {:else} <!-- item.ended -->
                        {#if item instanceof Listing}
                            <h3 class="text-2xl text-center my-2">
                                Sold out
                            </h3>
                        {/if}
                    {/if}
                    {#if item instanceof Auction}
                        {#if item.start_date && item.end_date}
                            {#if item.end_date_extended}
                                <h3 class="text-2xl text-center text-warning my-2">
                                    Time Extended
                                </h3>
                            {/if}
                            {#if item.started && !item.ended}
                                <div class="py-5">
                                    <Countdown bind:this={finalCountdown} totalSeconds={item.ends_in_seconds} />
                                </div>
                            {/if}
                            {#if !item.reserve_bid_reached}
                                <p class="my-3 w-full text-xl text-center">
                                    Reserve not met!
                                </p>
                            {/if}
                        {/if}
                        {#if item.bids.length}
                            <div class="mt-2">
                                <BidList auction={item} />
                            </div>
                        {/if}
                    {/if}
                </div>
                </div>
                <!-- BIDS END -->
            </div>
        </div>
    </div>
{/if}
