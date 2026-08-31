# Pricing is a product surface

- **URL:** https://arnon.dk/pricing-is-a-product-surface/
- **Author:** Arnon Shimoni
- **Published:** 2026-05-05T14:48:57+00:00
- **Modified:** 2026-05-05T14:48:59+00:00
- **Type:** post
- **Topics:** billing
- **Reading time:** 5 minutes
- **Description:** SaaS freemium fails for AI. With high GPU costs, pricing must be a dynamic product surface. Learn to gate intensity, outcomes, and compute instead of features.

Pricing isn’t an annual finance exercise where the CFO and the head of sales argue about a spreadsheet for six weeks. It used to be, but it isn’t anymore.

It’s a

surface

because customers touch it more often than they touch most product features. Not only that, it helps self-select customers when they browse your website.

The piece most teams still get wrong is the AI freemium part because the instinct from a decade of SaaS is to give the basics free and gate the best features but in AI, that math doesn’t hold.

What’s changing?

Vikas Kansal who leads PM for Google AI, had a piece up on Lenny’s newsletter today

walking through what they actually learned shipping subscriptions on top of a frontier model. The tl;dr is the traditional SaaS freemium playbook (give the basics free, gate the best features) does not survive contact with AI economics.

I agree for two reasons:

The

cost shape

changed. In SaaS, an extra free user costs roughly nothing. The marginal compute is a database read and some bytes over the wire. In AI, every “Enter” press fires GPUs. Free tier usage shows up on the bill in real dollars, not fractions of a cent. Vikas’s says it as “every time a free user hits ‘Enter,’ your GPUs fire, and your cash burns”. Cool…

The

value shape

changed. The best frontier models are good enough on the free tier that users start asking why they should pay. Vikas writes that Gemini Advanced power users were saying “why should I pay $20 a month when the free version is already smarter than I am?”, which is definitely not a marketing problem you fix with a paywall. That’s the free product eating away at the paid product on capability.

You can try to paywall the magic, but then you kill the WOW that earns the upgrade. Vikas calls this the AI freemium paradox where either the free tier eats the paid tier, or the paid tier never gets the chance to land because the free tier never showed the magic.

Oof.

WWGD? (what would Google do?)

What the Google AI team landed on is a three-pillar paywall mapped to where the cost actually lives. None of them are the SaaS freemium playbook.

Gate intensity, not features.

Plus / Pro / Ultra tiers in the Google AI bundle gate volume: Higher tiers get larger context windows (up to 1M tokens), more prompts, longer sessions. A casual user gets a taste on Pro. A power user, whose unit economics would otherwise be terrifying, pays Ultra. Midjourney does the same with Fast Mode vs. Relax Mode… you’re paying for priority access to GPU minutes, not better images.

Gate outcomes, not access.

The free tier produces an answer whereas the paid tier produces a finished task. Intercom’s Fin is the cleanest version of this… $0.99 per resolved support ticket. Free to attempt and you only pay when the customer confirms the problem was actually fixed. The paywall is on the unit of work the buyer cares about, not on the feature.

Gate the heaviest compute modalities.

Text is cheap so sure, give away a 500-word email. A cinematic 3D world model is not. Genie 3 sits at the top of the Google AI ladder because the TPUs to serve it at consumer scale don’t exist if you serve it for free. Customers intuitively get this… The heavy modalities are a natural top-of-ladder upgrade trigger, and pretending otherwise is how you lose money.

Pricing needs to iterate

Pricing has to iterate, probably more often than most teams are comfortable with. Lovable changed pricing more than ten times in their first year. Annual plans, credit rollovers, top-ups, removed seats as a unit, new business plan, currency expansions, downgrade flows, promos – all went past the customers and no one revolted (at least not yet).

For AI specifically, the iterations matter more, not less because the cost basis of your product moves like, all the time. If you cement your pricing you’ll bleed margin and cap your growth which is a dangerous combo.

Treat pricing as hypotheses to test, not architecture to defend. And by god, don’t start a monetization committee. Internalize that you don’t know the right model in advance and play around with stuff.

P.S.

“But my customers hate price changes”

, yeah – because the only change is upward, and it’s always tied to a press release. If you change pricing constantly, in both directions, with promos and downgrades and free taste-tests and usage tweaks, customers will no longer just think you’re being hostile.
