# Notes on AI Led Growth (ALG)

- **URL:** https://arnon.dk/notes-on-ai-led-growth-alg/
- **Author:** Arnon Shimoni
- **Published:** 2026-03-12T16:18:59+00:00
- **Modified:** 2026-03-15T18:28:01+00:00
- **Type:** post
- **Topics:** billing
- **Reading time:** 10 minutes
- **Description:** PLG had a good run, but it's not enough anymore. AI is changing how software gets discovered, bought, and expanded. Credits are emerging as the core commercial primitive. Not as a pricing model, but as infrastructure. Notes on what ALG means for billing, growth, and the go-to-market playbook.

PLG had a good run. I was a big fan, too.

For the last fifteen or so years, all companies had to do was build something developers or users loved, let them sign up with a credit card with Stripe, measure activation and expansion, and eventually hire sales when the deals get big enough.

Stripe made it trivially easy to charge a credit card. Segment, Amplitude, Mixpanel, and Customer.io made it really easy to measure what users did after they signed up and the entire SaaS growth stack was built around one assumption: a human signs up, a human uses the product, a human decides to pay more.

PLG isn’t really a goal anymore

I’ve spent the last two years working on billing infrastructure for AI companies, and 4 years before that building products that had PLG as the main goal.

SLG is now the way companies actually make money. It’s still easier to make money when you have a good PLG motion, but it’s not enough.

The past year also showed me that companies build products where the primary consumer of value is increasingly not a human clicking buttons in an app or a browser anymore. It’s an agent making API calls. A workflow running autonomously. A model consuming tokens on behalf of a user who may not even know it’s happening.

PLG and SLG weren’t designed for this, and that’s fine – so now with AI very clearly changing every phase of the buying process, from awareness through renewal…

What I want to do here is add notes from the infrastructure side – because the operational details of ALG are where things get interesting for me.

How people find and buy software is different now

Think about how you researched your last tool purchase.

Did you Google it? Probably not first. You probably asked some AI or Perplexity something like “what’s the best X for Y” and got a synthesized answer.

That’s how I often discover new things today.

This is already ravaging the PLG content playbook. Write blog posts, rank on Google, capture intent. That whole funnel is leaking from the top. People are calling the new game Answer Engine Optimization (AEO). I’m not sure it’s actually

that different

, but you do need to show up in AI-generated answers or you’ll be invisible.

The buying side is changing too. More companies are using AI to continuously evaluate their own vendor stack. Not at QBR time once a quarter, but continuously.

Churn in an ALG world isn’t really a decision someone makes in a meeting anymore. By the time a human is involved, the change has already happened.

Credits are infrastructure, not a pricing gimmick

I

absolutely hate credits

. I’ve written about it many times. Unfortunately I can’t keep fighting it. Everyone’s talking about credits, mostly as a pricing model.

I think that misses the point. Credits are an architectural decision that happens to have pricing implications.

I think that’s why I hate it too – because it’s often just a hack that serves to get you to pre-buy stuff you don’t need. That’s almost like a gift card (which is how many many products implement it). A balance that goes down. That works for simple prepaid stuff.

For actual stuff you’d use in a company, you start needing credit pools, and rollovers, and expiration that you can extend, and burn down against different rate cards depending on which model ran the inference, or enforce hard limits in real time before you end up racking a $50,000 bill overnight

like my friend Amos did.

I think getting this “right” means treating credits as a ledger primitive. Wallets and credits are distinct, composable objects.

A wallet has rules (rollover, expiry, sharing).

Credits have rates (which vary by model, by tier, by negotiated contract).

Tokens are consumed and metered.

The consumption event, the rating logic, and the balance management are three separate concerns that need to work together.

Snowflake understood this early. Their credit architecture isn’t a pricing layer bolted on top, but a foundation the entire business model sits on. Most AI companies today are trying to get to the same place using some gift card primitive and a lot of custom code. It works until it doesn’t.

Snowflake’s pricing is… intense…

Credits as a growth lever

Steven Forth wrote a detailed piece on AI Led Growth recently

, and one observation in it deserves more attention: credits aren’t just how you charge but how you grow. Steven is right, and this also aligns with my

previous notes on seat pricing no longer being a growth lever

– so I’m happy for it.

In PLG, virality was the structure – Slack spread because every message was an implicit invitation. Figma spread because every shared design file was a product demo. Dropbox spread because shared folders pulled non-users into the product.

AI products don’t spread the same way, and the viral mechanics have to be engineered differently.

That’s a completely different thing from, say, a 14-day trial with a setup wizard.

A

Business Insider piece this week

captures why: Greg Brockman said “The inference compute available to you is increasingly going to drive overall software productivity”, and Tomasz Tunguz from Theory Ventures says they are already tracking tokens as a fourth compensation component alongside salary, bonus, and equity.

So it seems when you gift credits, you’re giving away something with genuine economic weight in 2026 – this isn’t the same as the old token/credit which was just an entitlement.

I am thinking a lot about what this kind of gifting unlocks. If built properly, the credits can still expire to speed up onboarding. The clock creates urgency without the pressure of a sales deadline.

You can gift credits scoped to a new use case or new product when a customer is already running your product – and now the expansion conversation is very different.

In enterprise deals, you can use a time-bounded credit allocation to subsidize the internal proof-of-concept that procurement needs to see before they’ll approve a wider rollout. You’re also therefore attaching a value to this credit which you can show on the list of deliverables / invoice.

The old referral program can also be re-architected with credits – a credit gift for someone moving to a new company turns them into a distribution channel. The champion’s credibility at the new employer does the selling.

Scaling without adding seats

By now you should know that in PLG, scaling meant more seats. More users, more teams, more departments. Growth was tied to human headcount.

ALG goes a different route – because a product approved for one workflow can expand to adjacent ones without onboarding new users or running change management programs. Scaling is now how much confidence you’re putting in a product, not how many humans log in to it.

Stop and read that again – because this is a big deal.

Now expansion looks more like infrastructure scaling than classic land-and-expand. The customer success conversation is no longer “let’s get more users onboarded” – it has become “are your users activated?” to “are you confident “are you confident enough in the results to expand to the next use case?”

Credit budgets become a sort-of proxy for that confidence. My experience shows that when the results are good, organizations top up credits and expand scope. Sometimes that means more people, but often more use-cases. Often that happens without sales involvement.

When results aren’t good, no amount of CSM effort saves the account.

Transparency wins as always

My chief complaint with credits and tokens remains that they are pretty opaque. They are often proxies for compute and inputs, and not outcomes or benefits.

There are two kinds of transparency that matter in ALG.

Two kinds of transparency matter in ALG – value transparency and pricing transparency

Value transparency

Value transparency means making outcomes visible and measurable.

When a product executes a workflow, the outcome is timestamped, logged, and attributable. Value is no longer something you narrate at a QBR or in a CSM meeting – it is something the system produces in real time.

This can be a mini dashboard or something showing what the AI did – it doesn’t need to be very fancy.

Pricing transparency

The second is pricing transparency. Credits

can

be a vehicle for clarity or a new type of opaqueness. It’s often the latter, unfortunately.

Take a look at the snowflake example from before again. Obscure units, price them at rates that hide the per-outcome cost, and bundled in ways that make comparison impossible.

Nobody is fooled by that for long. Churn WILL come for customers who are tricked by opaque pricing.

What I strongly recommend: publish consumption rates by workflow type. Map business inputs to credit budgets. Keep pricing stable over meaningful time horizons.

And for gods sake, make the boundary between billable and non-billable actions unambiguous.

The fastest way to destroy trust in a credit model is for a buyer to discover that failed tasks and system overhead are eating their balance.

Infrastructure has to catch up

I see the infrastructure gap every week. Companies trying to run AI Led Growth on billing systems designed for PLG hit the same walls:

Credits don’t work as first-class objects. They’re gift cards or wallet hacks – which means you can’t roll them over or enforce them.

Rate cards can’t flex. We know AI pricing changes constantly with new models getting released, but if eevery pricing change requires an engineering sprint, you can’t iterate at the speed ALG demands.

B2C and B2B live in different systems. This one is often forgotten – because self-serve checkout for consumers and custom enterprise quoting for sales-led deals run through completely separate stacks. The split creates reconciliation nightmares and makes it impossible to have a single view of revenue.

There’s no infrastructure for continuous evaluation. I find that most billing and AR systems can track some consumption events but can’t connect them to business outcomes. If the buyer wants to measure value, they’re building that measurement layer themselves.

None of these are unsolvable. Heck, I’m trying to

solve just that at Solvimon

. But they’re not problems that a homegrown system built around an off-the-shelf PLG billing system were designed to solve.

They need billing infrastructure that treats credits, usage metering, rate cards, and margin tracking as first-class concerns from the start.

So what now

If ALG is real, and to me the pieces are there, then a lot of the SaaS go-to-market playbook needs updating.

Mostly – pricing needs to be a real-time system, not something you revisit once a year, and billing infrastructure needs to support all of this without requiring a dedicated engineering team to keep it running.

The term “AI Led Growth” might not stick but credits as the core commercial primitive unfortunately will.

Continuous evaluation replacing a once-a-year big pricing update, scaling that decouples from headcount growth, and transparency as a competitive advantage rather than a vulnerability.

I wouldn’t wait this trend out. Every quarter you (or someone on your team) spends duct-taping credits onto a billing system that wasn’t built for them is a quarter your competitor spends compounding on infrastructure that was.

The best time to rebuild your billing infrastructure was before you needed to. The second best time is before your buyer’s AI figures out you should have.

More in my series on billing:

1,800 pricing changes in 2025, zero billing overhauls

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

I used Nano Banana 2 for the header image
