# Building a billing system is still hard, even with AI

- **URL:** https://arnon.dk/building-a-billing-system-is-still-hard-even-with-ai/
- **Author:** Arnon Shimoni
- **Published:** 2026-02-02T21:18:50+00:00
- **Modified:** 2026-02-02T21:18:53+00:00
- **Type:** post
- **Topics:** billing
- **Tags:** billing, monetization
- **Reading time:** 3 minutes
- **Description:** 8 years building billing systems and I’m still wrong about just how hard it actually is. Not “getting better at it hard”, but like really genuinely discovering new layers of complexity I never saw coming. — Back when we started Paid at the end of 2024, I remember people telling me “billing is not hard, […]

8 years building billing systems and I’m still wrong about just how hard it actually is.

Not “getting better at it hard”, but like really genuinely discovering new layers of complexity I never saw coming.

—

Back when we started

Paid

at the end of 2024, I remember people telling me

“billing is not hard, it may be tedious but it’s not that’s not that hard”

.

That person was wrong then (I didn’t push them on this too much) – and they’re still wrong today.

Yeah yeah, sure, AI made the coding part easier but it didn’t make the software engineering easier.

Coding the stuff was never the real bottleneck – not in the last 10 or so years anyway. The bottleneck is figuring out what needs to exist in the first place – what needs to be coded to make a consistent, useful system.

Consistent and useful doing heavy lifting there.

I’m still dealing with this today:

Say a customer buys 1,000 credits in January. They use 800. What happens to the remaining 200?

Seems straightforward until you layer in each company’s different models nad realities:

upgrade mid-cycle to a plan that includes 500 free credits

credits expire at different dates

a promotional credit pool that takes precedence

they request a refund but want to keep 50 credits

renewal happens but they’re switching from monthly to annual

have three subsidiaries each with their own credit pools that can’t intermingle

… the list goes on

So which credits burned first? Which rolled over?

Which expired? How do we do revrec under ASC 606?

That’s not a coding problem. That’s a

conceptual

problem.

You can’t Claude Code your way out of “What does correct even mean here?”. Not right now anyway.

—

The bummer is you also can’t validate these decisions until you’re deep in production with real customers, and you experience these very real edge cases you never imagined, that will cost you the contract with that customer.

I’m three years in,

Solvimon

is just over 3 years in too.

We have brilliant engineers. We have the AI, and we still run into cases where someone asks “what should happen here?” and it’s not hyper clear.

Billing isn’t a feature or a checklist – it’s a consequence of every business decision you’ve ever made about how you charge customers.

It’s the very interesting intersection of sales promises, legal, financial compliance, product functionality, and customer expectations (both our customer and their customers in-turn)

For this, you need really excellent systems thinking.

The problem didn’t get easier.

If you’re building billing infrastructure – whether internal or as a product – and someone tells you “we’ll just use AI to build it, I’m not worried” – they’ve never actually built it.

Respect the problem.

(Georgi and I both understood the problem, and luckily didn’t underestimate how hard it’d get to solve)
