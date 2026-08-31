# Extend or replace – how to evaluate your billing stack at AI scale

- **URL:** https://arnon.dk/extend-or-replace-how-to-evaluate-your-billing-stack-at-ai-scale/
- **Author:** Arnon Shimoni
- **Published:** 2026-03-15T21:38:13+00:00
- **Modified:** 2026-03-15T21:38:17+00:00
- **Type:** post
- **Topics:** billing
- **Tags:** billing
- **Reading time:** 15 minutes
- **Description:** I managed billing for 200+ price points and 14 engineers. Here's the 6-question framework I wish someone gave me to decide whether to extend or replace a billing stack at scale.

I wish someone had written this post for me five years ago when I was running billing at a global streaming company.

It was my first B2C company – 29 or so markets, 209 active price points and thousands of active discount campaigns. We had country managers who needed pricing changes live across our own system, Play Store and App Store all at once.

The monetization team was 14 engineers.

We started with a reasonable setup – a billing platform, a subscription middleware layer, some custom orchestration to handle market-specific logic. It worked. Over time, bundles were added, campaigns to allow trials with market-specific phases, then partner integrations with different revenue shares and activation models.

Then a second checkout flow.

Then gift cards.

Then, “credits” (think Audible’s credits).

Each addition made sense when proposed but together, they created a system where those 14 engineers spent most of their time maintaining the glue between systems instead of building anything new.

Billing complexity compounds in a way that’s invisible until you’re already deep in it

, and I’m afraid not many people get that.

I left that world and spent years helping AI companies figure out monetization (

first when I cofounded Paid

, now

at Solvimon

). Between the two, the architecture is different, but the pattern is very similar: credits instead of gift cards, and model-based exchange rates instead of seat-based pricing. Usage metering instead of subscription phases.

However, the billing sprawl looks the same every time.

If you just joined a company to own billing, or you’re an engineer who’s been handed the billing platform you’re about to face the same fork in the road:

Do you extend what exists, or replace it?

This is the most expensive decision you’ll make in your first year. The longer you wait with this decision, the more difficult it gets down the line.

Here’s

my framework

which I wish I had earlier:

What you inherited

Before we get into the assessment, let’s look at what a typical AI billing stack looks like from above.

This is an incredibly simplified version of a billing system handling 3 types of customer flows.

Billing sprawl is a real problem.

Each block often connects to more than just one other system, and that’s custom code that someone has to maintain. Each block is MULTIPLE failure points. Each of these is a reason why a month-end close cycle takes 2 weeks instead of 2 days.

At the streaming company, our version of this diagram had even more boxes. Subscription middleware translating between channels and the billing platform. A separate entitlements service with its own override logic (I’ve written

about why you need that separation before

). A payment middleware layer handling orchestration, refunds, and payouts.

When you have a simple PLG flow, that’s not a problem. When you’re handling 160,000 combinations and channels, things get complicated.

This is a real example of a B2C company’s monetization levers, with 160,000 combinations that needed routine testing.

Every block represented code. Every piece of code represented an engineer who wasn’t building product.

Why companies build billing system – and why it works for a while

I need to be honest here, because the “just buy something” take is too simple.

The “just code it yourself” is very enticing, especially with AI. Building your own billing DOES give you real advantages:

Total control over business logic.

At the streaming company, our market-specific pricing rules were genuinely unusual. Trials that varied by country. Bundle structures that changed quarterly. Partner revenue shares with custom splits. No off-the-shelf billing platform in 2018 could handle all of it. Building gave us the flexibility to model exactly what the business needed.

Deep integration with the core product.

Entitlement checks happened in-line. No latency from external API calls. No sync issues between “what the billing system thinks” and “what the product actually delivers.” When you own the code, you can make billing invisible to the user.

No vendor dependency.

There’s a legitimate argument that billing is too critical to outsource to a vendor who might change their API, raise prices, or

get acquired like Metronome

.

These are real and I’d never tell someone they were wrong for building.

No, I’m lying – I would. These advantages are front-loaded but the costs only come by later.

Within a year of having our own billing system, it was already 50%/50% buillding/maintaining and by the second year it was already 80% maintenance and just keeping the lights on. That is keeping tax codes updated, edge cases, and cross-system reconciliation.

What started as a superpower became handcuffs that I felt completely trapped in. Every change required four teams. Yes, the commercial teams could deploy new pricing – but that required a specialist helping them 100% of the time because there were simply too many systems to check.

Sound familiar? It should. Add proration, tax handling across markets, customer hierarchy, revenue recognition – each one that was manageable alone will eat your time and frustrate the organization.

Unless you KNOW the rest of the org feels the same way as you – you probably don’t want to build it long-term.

6 questions to diagnose your monetization stack

These are the questions I wish someone had given me before I spent two years extending a system that had already hit its ceiling.

I’ve gone through RFPs and RFCs, so I can be trusted.

1. Where does pricing logic live?

Where are the pricing calculations?

If they’re scattered across microservices, embedded in API middleware, hardcoded in config files you DEFINITELY have an orchestration problem.

Are they on the website, in pricing pages, in the CRM, in the ERP, and in the data warehouse too?

If every new pricing model means touching application code – you need to change something.

At the streaming company I was at, pricing logic lived in at least four places: the billing platform, the subscription middleware, the market-specific based product catalog, in the Google Play and App Stores,

plus

a set of business rules that determined what combinations were allowed.

Changing a price in Norway meant updating three systems and hoping the fourth didn’t break at month-close with the ERP.

Test yourself:

If pricing logic lives in your billing system as configuration, you have room to extend. If it lives in code wrapped

around

your billing system, you’ve already outgrown it.

2. How many systems does a single invoice touch?

Trace the path from “customer uses the product” to “customer receives an invoice” – count the systems – all of them.

Metering, rating, billing, tax, payment processor, ERP, CRM, commercial website, app, entitlements…

If the answer is 5+, your orchestration code is probably growing with every product line and market that you add.

When companies tell me they’re on Stripe – I find that they’re usually on Stripe + a custom entitlements service + a metering pipeline + a reconciliation script + a spreadsheet at the very least. Yes, Stripe handles the payments fine. The problem is the code you write around it, meaning the layer that connects Stripe to your pricing logic, your entitlements, your usage data, and your finance team’s close process. That layer is your actual billing system. You just don’t call it that.

I, too, learned that the hard way when going through a big audit.

3. Can any product team ship something “paid” without creating more work for you?

This was the test we always failed. Country managers wanted to run a promotional bundle. If it fit within the terms pre-defined years ago – that was fine. For anything else – it required changes to the product catalog, the subscription middleware, the entitlement overrides, and the billing calculations, the checkout pages, and synchronization between 3 teams, four tickets, and at least 4 days of work.

If your product org needs billing engineering every time they want to put a price tag on a feature, you’re rate-limiting your own monetization.

At AI companies shipping weekly and sometimes daily, this adds up fast.

4. What happens when a self-serve customer wants an enterprise contract?

This is where most AI billing stacks don’t really work well.

Nearly 100% of people I talk to have a manual process for this. That’s OK when you’re small. Your self-serve runs through Stripe, enterprise runs through Salesforce CPQ, or worse, a spreadsheet and a Slack thread with finance.

Two billing workflows, two data models, one finance team trying to reconcile them at month-end and figure out what was actually billed, what should be billed, and what the customer got (This also hurts customer support!).

If the answer is “we manually migrate them to a different billing flow”, you’ve definitely found the ceiling. I call this

“Billing v1”

.

Extending a PLG billing stack to handle SLG doesn’t work by adding more code around it. The architecture needs to support both motions in one ledger – what I’ll call

“Billing v2”

.

5. How long does it take to close the books?

If the close cycle is 2 weeks, finance will start having problems. When finance is spending those 2 weeks reconciling billing data against revenue recognition against the ERP, because each system has a slightly different version of reality – that’s a real problem.

Ask your finance team where the time goes. If the answer is “figuring out discrepancies between systems” – you can’t extend your system any further. The discrepancies exist because the systems are separate.

(And if you think revenue recognition is simple,

here’s my favourite PDF – a 64 page set of IFRS-15 rules.

)

6. Can you change pricing without an engineering sprint?

AI pricing moves fast. Credit exchange rates between models. New usage tiers. Committed spend discounts. Restructuring how you bundle inference and fine-tuning.

Test it as concretely as you can: how fast could you roll out a 20% discount for annual commits on your mid-tier plan?

And I don’t mean just in the billing system – I mean on pricing pages, in dashboards, in the revrec, in the CRM… If the answer involves engineers, a staging environment, and a deploy pipeline you’re looking at the ceiling.

Score yourself

Red flags

Zone

What it means

0-1 🚩

Extend

Your stack has real headroom. Clean up the orchestration code, automate the close process.

You’ll get 12 months before you revisit.

2-3 🚩🚩🚩

Grey zone

This is where most companies land. Yes, you can extend, but each extension adds code that makes the eventual replacement harder.

Are you extending the billing system, or the workarounds around it?

4-6 🚩🚩🚩🚩🚩🚩

Replace

Your architecture has hit its ceiling. Extending means building v2 on top of v1.

You’ll maintain two systems during a migration that never completes.

Estimating the real cost

Be honest here, because most build-vs-buy analyses compare the wrong things. You end up comparing feature-sets and the “contract cost” vs engineering salaries and call it a day.

I firmly believe that misses most of the actual cost on both sides.

The cost of extending

Direct FTE cost.

Count the engineers who spend >50% of their time on billing. At some companies hiring senior engineers for billing, the salaries are $300-450K fully loaded, meaning a 3-person billing team is $900K-$1.35M/year.

At the streaming company, our 14-person team was upwards of $1.5M annually and that was in a lower-cost market!

Opportunity cost.

This one is really hard so no-one does the math. My 14 engineers could’ve been focusing on higher-growth initiatives. Those 3 engineers you’re hiring for billing could be building product, improving inference, shipping integrations that drive revenue with partners.

At a company growing 3x YoY, the compounding opportunity cost of an engineer maintaining billing code is enormous.

Coordination cost.

Every pricing change that requires cross-team work has a cost: meetings, tickets, QA, staged rollout, rollback plan.

At the streaming company, a simple bundle change consumed 40+ person-hours across four teams. Multiply by the amount of pricing changes per quarter.

Revenue leakage.

Systems with manual reconciliation leak. 1-3% is common in companies with complex billing. On $10M ARR, that’s $100-300K/year you’re not collecting.

Close cycle cost.

A 2-week close means your finance team spends half its time on reconciliation. It also means decisions based on data that’s 2-6 weeks old.

You may not care, but the finance team DEFINITELY does.

Total: $1.5M-$3M+/year

at AI-scale companies, but it grows with every product line.

The cost of replacing

Platform subscription.

Billing infrastructure platforms (Solvimon, Orb, Lago, Zuora, Paddle, Recurly – depending on your needs) typically charge based on transaction volume or revenue processed. For an AI company at $5-50M ARR, expect $50K-300K/year.

Migration cost.

The big upfront number. Plan for 2-4 engineering months of integration work, plus 1-2 months of parallel running. That’s $150-400K one-time, depending on complexity. Some companies like Solvimon do the migration for you, others like Zuora ask you to hire your own consultants to do it.

Ongoing maintenance.

Even with a platform, you’ll maintain some integration code. But it’s the integration layer, not the billing logic itself. Budget about 1/4h of an FTE.

Total: $250-500K year one (including migration), $100-350K/year ongoing.

The real challenge for me with replacing was never cost, but the risk and disruption of migration – which was real and it’s scary. No one wants to hear it – but it IS a one-time cost. The cost of extending is permanent and growing.

What your billing system actually needs to handle at AI scale

Whether you build or buy, here’s the checklist. If your current system can’t do these things

without orchestration code around it

, it will become your bottleneck.

Credit architecture.

Not prepaid balances that decrement (that’s Stripe’s gift card model). Composable credit primitives: wallets, burn-down tracking, pooled organisational credits, exchange rates between models. When credits burn at different rates for Opus 4.6 vs. Nano Banana 2 vs. fine-tuning, that’s a ledger design problem. Bolt-on credit systems collapse under multi-model pricing.

Hybrid monetization in one ledger.

Subscriptions + usage-based + credits + committed spend with overage. All in the same system. Not Stripe for self-serve and a spreadsheet for enterprise. One ledger –> one close cycle –> zero reconciliation between systems.

Pricing as configuration, not code.

Rate cards, exchange rates, tiered pricing, per-customer overrides, all without engineering. When your commercial team wants to test a new packaging structure, the answer should be “configure it” not “ticket it”. I could never solve this at the streaming company with 14 engineers. Every pricing change was a deploy.

Usage metering with real-time visibility.

Consumption data can’t be a batch job at month-end. You need real-time visibility so you can enforce entitlements, surface usage alerts, and bill correctly. Without this, customers get surprised by invoices and support absorbs the fallout.

Entitlement management.

What the customer can use, based on their plan, credits, committed spend, org structure. I’ve written extensively about why this should be separated from billing logic but it still needs to be connected to the billing source of truth. Entitlements in a separate system with no sync –> drift –> support tickets.

PLG-to-SLG expansion.

When a self-serve customer wants an annual commitment, the transition should be a config change, not a data migration. Same ledger, same customer record, different terms.

Revenue recognition for consumption models.

ASC 606 / IFRS-15 on usage-based and credit-based pricing is genuinely hard (remember that 64-page PDF?). Revenue data, contract data, and billing data need to live close together. When they’re separate, reconciliation becomes the work.

Audit-ready data by default.

Immutable ledger entries. Full event history. Every change traceable. Not as a feature you enable later as a core property of the architecture. If your billing system doesn’t produce audit-ready data natively, your finance team is rebuilding that layer in spreadsheets.

What the target state looks like

You may feel like this isn’t that different.

For me, it very much is. Because everything is in one system – when pricing, metering, credits, entitlements, invoicing, and revenue data live in one system, the orchestration code disappears. The complexity didn’t go away. It moved from your codebase into infrastructure designed for it.

Now you’re not keeping as many systems “in check”.

The extend trap

The crossover happens around month 8-10 in most cases. Before that, extending looks cheaper. After that point, the gap only widens.

The most common mistake is choosing extend for the right short-term reasons and staying too long.

Trust me, I’ve been there – extending feels responsible. Lower risk. No migration. You can show progress in a few weeks to months. Your team knows the system, and there’s no feeling bad about the sunk cost.

But again – every extension adds orchestration code. And orchestration code compounds. The credit system you bolt on today becomes the integration you maintain forever. The reconciliation script you write this quarter becomes the process nobody touches next year.

I watched this happen in real time. We spent 11 months extending the billing stack at the streaming company. At the end of it, we’d built billing v1.5 which was too customized to maintain, too patched to scale, and too entangled to replace cleanly. No vendor could do what we had built by that point.

The 14-engineer team was still 14 engineers.

Build-vs-buy isn’t useful

Seriously – forget the build-vs-buy framing. You should be asking

Is my billing system’s architecture capable of handling my pricing complexity in 18 months?

Not today because today everything feels manageable. The question is whether the

years

of decisions baked into your current stack on how it handles credits, how it connects PLG to SLG, how it feeds revenue recognition, how fast pricing can change are still going to be good for where you’re heading.

If yes

, extend. Seriously. Not every billing system needs to be replaced. Some have real headroom.

If no

, the cheapest time to replace is now. It only gets more expensive.

More in my series on billing:

Notes on AI Led Growth (ALG)

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
