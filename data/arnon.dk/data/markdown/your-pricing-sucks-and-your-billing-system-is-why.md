# 1,800 pricing changes in 2025, zero billing overhauls

- **URL:** https://arnon.dk/your-pricing-sucks-and-your-billing-system-is-why/
- **Author:** Arnon Shimoni
- **Published:** 2026-02-21T15:22:05+00:00
- **Modified:** 2026-02-21T17:43:01+00:00
- **Type:** post
- **Topics:** billing
- **Reading time:** 12 minutes
- **Description:** Your pricing page promises usage-based credits and hybrid plans. Your billing system runs on two duct-taped Stripe subscriptions and a spreadsheet. Everyone changed their pricing in 2025. Almost nobody changed what's behind it.

Everyone and their sister changed their pricing page in 2025

but very few changed what’s behind it.

I’ve spent the last few years of my life thinking about billing systems. First at Pleo, then at Storytel, then at my own startup (Paid), and now at Solvimon.

Well, I have some notes.

Not “hot takes”, but observations from watching hundreds of companies try to modernize their pricing while running billing infrastructure that was designed for a simpler time.

The tl;dr: your pricing sucks. Not because you’re bad at pricing but because your billing system literally cannot execute what you designed on your pricing page.

And the industry isn’t handling this well

Disclaimer: if you’ve ever invited Simon Kucher to help you, you already know this 😉

Everyone was panicking in 2025

Last year when I cofounded Paid, I was riding high on the “outcome pricing” wave. And among the top companies there were over

1,800 pricing changes

.

Kyle Poyar’s and Rob Litterst’s research says 3.5 average changes per company in 2025

.

Notable examples I remember include:

Unity tried a runtime fee and had to reverse it after developer revolt.

Docker jacked up their Pro plan by 80% initially, and then another 22% (

$5 to $9/month in 2024

, then $11 in 2025).

Figma bumped their Pro tier while freelancers complained the UX was getting worse.

Notion gated AI features behind a $23.50/user/month tier.

Canva raised prices and had to roll it back for loyal users in 2024.

I believe this was a sign of that industry-wide panic, because everyone simultaneously realized that their pricing model (that thing that’s supposed to capture the value they create) wasn’t working anymore.

AI changed the cost structure. Usage patterns became unpredictable. The old seat-based math stopped adding up, so everyone changed their pricing pages.

The pricing page is a work of fiction

Why am I saying that? Because I’ve seen lots of companies fail to actually implement the pricing they say.

Here are some examples:

Your pricing page says…

… but

Your pricing page says you do usage-based pricing with credits and a base platform fee…

… but your billing system says you have two separate subscriptions duct-taped together because Stripe can’t mix billing intervals in a single subscription. Annual platform fee on one subscription, monthly overages on another. And a sync job that tries to keep them, well,

in sync

.

Your pricing page says you offer flexible credit packages that roll over…

… but your system says credits are stored in a spreadsheet that your finance team manually reconciles every month, because your billing tool treats credits like gift cards, not like a unit of account.

Your pricing page says “contact us for enterprise pricing”…

… but the billing system says your RevOps’s “deal desk uses a Google Doc template and someone manually creates invoices in a different tool (like QuickBooks) than the one that handles your self-serve customers.

I’m not making these up, and they do get worse but I don’t want to embarrass anyone.

Why seat-based pricing broke

I’m gonna go back for a second, because seat-based pricing worked because the cost structure was predictable.

One user was roughly equivalent to one unit of infrastructure cost. Obviously, more users = more revenue, roughly proportional to more cost.

Easy to bill, easy to forecast, easy to understand.

Once we added AI to the mix, it dodn’t scale by user. It scales by tokens, compute minutes, model complexity. Think of one power user in Notion AI using up a ton of resources while others don’t use it at all. Your top 5% of users might be eating 75% of your compute costs. And you don’t even know it, because your billing system doesn’t track it.

Source:

Kyle Poyar, again, obviously

So now, some 85% of SaaS leaders say they’re using some form of usage-based pricing according to OpenView. 61% claim to be “hybrid.” But the tools they’re billing with were designed for

$X/seat/month

.

There’s this gap then between what the pricing page promises and what the billing system can actually do is growing every quarter.

And it shows.

78% of IT leaders reported unexpected charges

tied to consumption-based or AI pricing in the past year and 61% cut projects because of surprise costs.

Customers are getting bill-shocked because the system can’t give them (or you) real-time visibility into what they’re consuming.

xkcd 1739:

Fixing Problems

An aside: outcome based and value based pricing

This is also my fault, but in 2025 there was a popular narrative that “value-based pricing” is the answer to everything. Charge based on outcomes! Align incentives! If the customer gets value, they pay more!

I like it in theory and I still think it’s the holy grail but can we be honest about how hard this is to actually implement?

Value-based pricing assumes you can measure the outcome and for some products, that works (customer support tool, AI SDR, mortgage processing)… But what if you’re a B2B selling eSIM services? What’s the “outcome”?

The outcome is “someone bought an eSim”, and you can’t really charge more because the internet worked

better

, because it’s a commodity.

Your only real value metric is revenue share which is already how partnerships work in telecom and lots of B2Cs, and those deals are often handled outside the billing system entirely, in custom contracts and partner portals.

What if you’re a database company? The “outcome” is “queries returned results”? What if you’re a monitoring tool? The “outcome” is “nothing bad happened”? Try putting

that

on an invoice!

Value-based pricing

is

the holy grail, but for a lot of businesses it’s also a mirage and we have to be honest about it. The path from “we should charge for outcomes” to actually having a billing system that can track, meter, attribute, and invoice those outcomes… that path is paved with spreadsheets and broken dreams.

What most companies actually end up with is a hybrid: some seats, some usage, some credits, maybe a platform fee, and a bunch of custom deal logic on top. Which is fine! That’s realistic! But your billing system needs to actually support that hybrid reality instead of pretending the world is still

$X/seat/month

.

And no, the tools aren’t keeping up

I’m not going to bash products or vendors – they all had their reasons for building the way they did – but what I will do is describe some patterns that will be very recognizable to anyone who’s tried to do anything beyond simple recurring monthly billing:

You can’t mix billing intervals.

Want an annual platform fee with monthly usage overages? That’s two separate subscriptions. Good luck keeping them in sync when you start mid-cycle updates.

Pricing changes require migrations.

Want to change your per-unit rate? In many systems, that means creating entirely new pricing objects and migrating every customer to them. One by one…. Hope you don’t have thousands of them.

Real-time metering doesn’t exist.

Yes, most billing tools give you some periodic usage summaries – but not real-time. Which means you can’t notify a customer when they’re approaching a threshold. So you have to start tracking outside and duct-taping it. You can’t enable automatic upsells. You can’t even give your customer a live dashboard of what they’ve used.

Credits are an afterthought.

Lots of systems treat credits like coupons or gift cards, or a singular wallet, and not as a core architectural primitive that represents pre-purchased compute.

If you want credit pooling across products, credit burn-down tracking, or credits that convert differently based on what they’re used for you’re building that yourself. Duct-taping again.

The 20-product limit.

At least one major billing platform limits you to 20 products in a single subscription. If you have a modular product with lots of add-ons you have to start figuring out how to shuffle things together.

Custom sales-led deals break everything.

Your billing system was designed for self-serve. But now sales closed a deal with a custom “rate card”, a 90-day free trial on one product, and a committed spend discount that kicks in at month 6. Your system says “lol no”, and you hand it off to be handled in a spreadsheet.

Your finance team says “I’ll handle it in Excel.”

I’ll just build it myself

At this point some of you are thinking “fine, I’ll just build it myself”.

I have bad news, because I’ve written about it lots of times before.

I’ve seen a company estimate 3 months to build their billing system. It took over a year and by the time it was “done” it was already behind on the new pricing and business model. It took another 6 months to catch up. Granted, this was before you could ask Claude Code to help you, but that’s still a hefty job even if you don’t write the code yourself.

I’ve seen another company spend ~$2.5 million per year just to

maintain

their billing system (including the engineers they keep on it). That’s not to add lots of new features, not to make it better, just to keep it running and keep up with regulations and tax changes.

And look, I’ve literally worked on billing systems at Pleo, and then co-founded a company specifically to tackle billing. I know how deep this rabbit hole goes even when others don’t agree with me – they end up agreeing in retrospect after 10 months of dealing with edge-cases. I wrote a whole post about

the 14 pains of building your own billing system

and honestly, 14 wasn’t enough.

The problem isn’t that billing is hard to build. It’s that it’s

ongoing

and ever changing.

Yes, tax rules change across jurisdictions every few months. New compliance requirements pop up. Who’s doing SOC type 1 even?

Customers have edge cases that your system wasn’t designed for (and these aren’t edge cases at all – because they’re just… cases).

You don’t just build a billing system and move on – you adopt a billing system, and it becomes your permanent second product.

Where is this all going?

Unfortunately I don’t have a grand unified theory for you.

Sorry.

But here’s what I’m seeing anyway:

Credits are becoming infrastructure

As much as I hate them as a

buyer

, more companies are using credits as an internal unit of account and as a way to abstract over different types of usage (API calls, compute minutes, storage) into a single unit.

It’s not a gimmick anymore. Snowflake did this well (and it’s very complicated) – but most billing tools still treat credits like some rewards point system.

Entitlements are separating from billing

What a customer can

access

and what a customer

pays for

are increasingly decoupled. I wrote about this

years ago

and it’s becoming more true, not less. Your billing system tells you what they paid. An entitlement system tells you what they can do. These are not the same thing, and combining them is how you end up with

if plan == 'gold' then show_feature()

scattered across your codebase.

The “messy middle” is where everyone lives

Pure self-serve PLG billing is solved. Pure enterprise contract billing is solved (expensively). The messy middle (where you have self-serve customers AND enterprise deals AND usage-based components AND credits AND custom terms) is where most growing companies actually are.

And that’s exactly where the tools fail hardest.

Pricing will keep changing faster and faster

If the 3.6 changes per company in 2025 felt like a lot, buckle up because AI costs are still fluctuating. They’re not dropping!

Models are still evolving, and customers are still figuring out what they’re willing to pay for.

Your billing system needs to support pricing changes without engineering sprints. If changing a rate card requires a deploy… you’re going to have a bad time.

I’m sad to say that I don’t have a neat conclusion for you or a framework to follow.

Billing has always been messy and I’ve been saying this since my first post about it. What

is

different now is that AI compressed the timeline. The complexity that used to take a company at least 4 years is happening in year 2.

If you felt any of this viscerally, at least now you know you’re not alone. And if you’ve figured it out, genuinely, reach out. I want to hear your war story!

More in my series on billing:

Building a billing system is still hard, even with AI

Notes on where seat-based pricing is going

🐙 The 14 pains of billing for AI agents

🦑 The 14 pains of building your own billing system

Design your pricing and tools so you can adapt them later

How we built a Cashback system with Stripe

You’re pricing your SaaS wrong but that’s probably OK

You should separate your billing from entitlements

5 things I learned while developing a billing system

Notes on AI usage in preparing this article:

I used Nano Banana for the header image

I used Perplexity to verify some of the details

I asked Claude to help me something that felt off with my structure, with the prompt

"Is there something weird about the section about the value based pricing. Does it feel weird, misplaced? The segue to it doesn't make sense to me. Any suggestions?"
