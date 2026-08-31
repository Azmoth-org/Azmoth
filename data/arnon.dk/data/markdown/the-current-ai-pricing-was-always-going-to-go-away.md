# The current AI pricing was always going to go away

- **URL:** https://arnon.dk/the-current-ai-pricing-was-always-going-to-go-away/
- **Author:** Arnon Shimoni
- **Published:** 2026-05-22T11:24:39+00:00
- **Modified:** 2026-07-30T20:09:14+00:00
- **Type:** post
- **Topics:** ai, pricing
- **Reading time:** 6 minutes
- **Description:** The current AI pricing was always going to go away because it just doesn’t make sense. For whatever reason (lots of speculation) Microsoft canceled internal Claude Code licenses, there were widespread reports that Uber blew its entire 2026 AI budget in four months, and we all know GitHub has now dropped flat-rate plans across its […]

The current AI pricing was always going to go away because it just doesn’t make sense.

For whatever reason (lots of speculation) Microsoft canceled internal Claude Code licenses, there were widespread reports that Uber blew its entire 2026 AI budget in four months, and we all know GitHub has now dropped flat-rate plans across its products.

For many months I’ve been saying that “the AI subsidy era is ending”. Which is, politely, a way of saying that everyone was just jamming a bunch of AI features into every version of their product in an attempt to win market and hope that the inference costs would just keep falling.

They kind of did, but also they didn’t because the way the cost works doesn’t add-up. The labs have no choice except to pass that wrong cost curve along to the users.

Did we collectively forget second-order thinking?

Each model generation, costs per token did fall in theory, sometimes 10x less but that was for comparable quality… Lots of people extrapolated and built business models on the extrapolation, which… isn’t how you think about it.

Second-order thinking anyone?

This is Jevons paradox in real time

It’s not too far from induced demand (everyone who deals with road planning knows about it). Each new capability invents new demand. Highways are the textbook case. Add a lane, you get new commutes.

AI follows that exact same direction because cheaper inference doesn’t reduce the bill, it expands what people ask the model to do.

No one wants to stay on older cheaper models.

Sure, now my reasoning queries take >4 minutes, where the old ones took just 2… But my agent also makes 50 calls where the old prompt-based workflow made one. The total spend goes up.

Anyone selling a flat-rate “AI assistant” assumed user behavior wouldn’t change but it did, just like it always does.

The second is that the supply side stopped cooperating – memory and GPU economics are moving against you.

Memory got 4x more expensive. GPUs got >95% more expensive.

Frontier training and inference run on Nvidia accelerators paired with high-bandwidth memory. The ceiling isn’t transistors anymore, it’s HBM and the advanced packaging that bonds it to the compute die.

Morgan Stanley estimates the bill of material (BOM) on the new NVIDIA VR200s will be 95% higher – memory accounting for 435% growth ALONE.

That ceiling is really only one factory deep. TSMC’s CoWoS packaging line is and was the bottleneck for accelerator supply. SK Hynix dominates HBM (and has become a super popular company, with Samsung lagging and Micron behind that. None of them can add capacity overnight. These are 18-to-36 month commitments, minimum, and they were planned for a world that under-forecast demand by an order of magnitude.

So GPU pricing is what scarcity pricing looks like! The creme-de-la-creme of GPUs and TPUs and other types of accelerators are ~2x more expensive than the previous generation at a comparable cluster scale. HBM prices have 4x’d in 18 months. Power and cooling are now real constraints in places nobody used to model power for, which is why every hyperscaler now has a “we’re building a gigawatt campus” story and a nuclear-PPA press release – whether that happens or not.

Anthropic’s CFO testified under oath this March that

the company spent $10 billion on compute and made $5 billion in revenue (Ed Zitron has the math which seems right to me)

. The labs are completely underwater on compute and inference, so they’re raising prices to keep the lights on.

Companies that sold flat-rate AI-everywhere products are now sitting on a margin problem they architected themselves into. The bet was that one of these curves would bend in their favor. None of them did, probably none of them will, certainly not on the timeline their pricing assumed.

OK so what now?

The product question has to change because it can’t just be “let’s slap some AI chatbots”.

You’re a builder. Ask “which use cases earn the inference cost they burn?” because that’s literally your job. You have to make something that makes money, but that’s hard to do.

I know of three main architectures that handle the cost moving underneath. They’re not new, but they all matter – especially if you’re used to selling seats the old fashioned way.

Per-action

Every API call, every generation, and every agent step has a price.

Revenue scales with cost because they’re indexed to the same underlying event. This is what Twilio, AWS, and others do. The downside is that customers see the meter, and they negotiate. On the other hand, your gross margin doesn’t depend on guessing how hard your power users will hammer the system.

Credits

Prepaid buckets where a customer buys 100,000 credits, burns them down on whatever, refills.

Credits can help smooth cash flow and let you mix model costs behind a single unit, which is the only sane way to handle a product that routes between five different inference providers.

What you need to watch out for is “breakage” – that’s when credits later become stranded assets (like a gift card you forgot to or can’t use) and customers can’t tell which one they bought.

Hybrid!

Everyone’s favourite new thing (meaning, not really new), but: a base seat with included credits and metered overage.

Most enterprise sales motions I’ve seen accept this without too much argument, because a seat number (or “flat platform fee”) still anchors the contract and the meter is the safety valve. It’s the design most AI-native products converge to within their first repricing cycle. Again, not my favourite, but whatever, it tends to work!

The shape isn’t the point by itself, but rather whether

the line moves

when the cost line moves. Per-seat is the one architecture that pretends costs are fixed.

Everything else is some flavor of indexing revenue to the underlying event.

The impossible choice

If your pricing can move with cost, you get to keep building.

You can ship the agentic workflow, the heavier reasoning model, the slow expensive feature for power users, and you have a way to be paid for them.

If you’re locked into per-seat (or flat, or whatever) – you pick between two losing options. Eat the margin and watch it compress every quarter your customers’ usage grows. Or strip AI out of your cheaper tiers and watch your activation rate fall off the lower-priced cohorts that used to be your funnel.

Both options are visible on the next board deck.

Neither one of them looks fun.
