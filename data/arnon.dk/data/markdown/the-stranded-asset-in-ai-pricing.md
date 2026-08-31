# The “stranded asset” in AI pricing

- **URL:** https://arnon.dk/the-stranded-asset-in-ai-pricing/
- **Author:** Arnon Shimoni
- **Published:** 2025-12-10T21:51:57+00:00
- **Modified:** 2025-12-10T21:52:03+00:00
- **Type:** post
- **Topics:** pricing
- **Tags:** billing, monetization
- **Reading time:** 4 minutes
- **Description:** With hybrid "AI pricing", users face siloed entitlements, creating "stranded assets" where purchased credits remain unused. This misalignment leads to significant churn risks as companies reassess value versus spend amid rising AI costs and limited access to resources.

Oh boy – look at the clumsy mix of business models! The old world (seat based) is hitting the consumption-based AI credits… And of course, customers are the ones who deal with the wreckage.

The hybrid models everyone loves keep the seat price, but they add “AI Credits” on top – they protect margins and create a bunch of extra tiers. And to be fair, it’s a fair compromise – but it has created a user experience hostile enough to kill a renewal.

The friction point isn’t the price point – it’s

siloed entitlements

– which are creating things that customers pay for, but never get value from.

Figma’s credits in action

I spoke to a contract owner recently who manages a team on Figma,

who just rolled out AI credits

.

Figma’s AI credit pricing (

source: Figma

)

The owner’s reaction wasn’t: “Great, now we have access to AI”, but “this is theft. I’m paying for pools of credits that will never be used.”

Here is the mistake vendors are making: They are allocating consumption limits to the

User ID

rather than the

customer or org ID

.

What Figma is missing in this setup:

The Power Users (20%):

These will burn through tons of credits in a week, hit a hard limit and get blocked.

The Casuals (80%):

They use the tool, but they don’t use the AI. They sit on a pile of credits that expire at the end of the month.

This creates

“Stranded assets”

.

You have a bill that says you purchased 50,000 credits for your company, but because of how the pricing was designed your team can only access some of them. The rest are locked in the “wallets” or entitlements of inactive users.

It’s misaligned incentives

Maybe retrofitting a “Shared Corporate Wallet” is an engineering nightmare for them but I think they did this on purpose.

In the gift card industry “breakage” is the money companies keep when you don’t spend the full card – and

you can read a lot about this on IFRS 15 (who doesn’t??)

What Figma and others are doing with siloed AI credits is just that

Scenario

How the vendor sees it

How a customer sees it

User A (Heavy Usage)

“Upsell opportunity! They hit their limit”

“Fuck, I’m blocked”

User B (Zero Usage)

“Pure profit”

“Wasted spend. Why am I paying for this?”

The Admin

“Stable Revenue”

“Now I have to shuffle licenses… Great…”

The customer is the tenant, not the “seat”

If you are building a billing solution in 2026, you have to accept that the “seat” is no longer the atomic unit of value, and it’s not what delivers value.

It’s not a growth lever anymore. The work being done is the unit of value.

If a company buys 100 seats, they aren’t buying 100 separate relationships with you. They are buying one relationship that allows 100 people to work. If you charge for the seat, give the seat access.

But if you charge for the volume (credits, tokens, minutes), you must pool the entitlements or at least give that option.

Seriously don’t sell “breakage” as a feature

We are entering an era where software is becoming expensive again when the bill for AI features hits thousands of $ a month.

AI mandates from boards meant customers were buying hundreds of tools just to be AI-forward, but they will not tolerate this for long.

They will look at their utilization reports and see that they’re paying for nothing – and they will churn.

It’s become easy to bring in AI, and it has also become much easier to churn.

Source:

Kyle Poyar’s Growth Unhinged – The AI Churn wave?
