# You gotta deal with the boring part first

- **URL:** https://arnon.dk/you-gotta-deal-with-the-boring-part-first/
- **Author:** Arnon Shimoni
- **Published:** 2026-06-24T10:58:00+00:00
- **Modified:** 2026-06-24T11:00:32+00:00
- **Type:** post
- **Topics:** ai, marketing
- **Tags:** ai
- **Reading time:** 11 minutes
- **Description:** Since 2024 the role of the CMO or marketer in a startup has really changed. Mostly, everyone has the same tools so everyone is producing the same slop at the same time. I can no longer remember times that I’ve read content that looks and sounds exactly the same. They organize cool dinners and then […]

Since 2024 the role of the CMO or marketer in a startup has really changed.

Mostly, everyone has the same tools so everyone is producing the same slop at the same time.

I can no longer remember times that I’ve read content that looks and sounds exactly the same. They organize cool dinners and then post about how it was “No slides, no pitches, just good people sitting down for dinner”.

Because the tools (meaning, Claude) is a super commodity, the output that worked in 2024 before everyone else adopted it – just doesn’t anymore.

So now, the only way to level up is to stop prompting Claude for your next post and start building a system underneath it. I suspect this will work for a bit longer because it requires a little bit of creative thinking, and not everyone has the mindset for that.

Think about it like a contractor

In late 2024

I started my own company

and I was the lone marketer from inception and through two funding rounds. It wasn’t super long before I brought in a few contractors to help with content.

These contractors were a little bit more freelance, but some were running elaborate positioning businesses but even they couldn’t produce something that sounded like us or fit what we needed until we had the system in place.

That means the positioning, the ICP, examples of what good actually looked like. Without that, even the most talented people just guess at your taste and often miss the mark.

AI is the same. Treat it like a contractor who can do an enormous amount of work, fast, and who knows nothing about your business until you tell it.

You build the base yourself, by hand. That means feeding it:

customer interviews (both good and bad)

your competitors

your positioning

what you’re actually thinking about

anecdotes that come up during calls and meetings

who you want to sell to

who you’ve

actually

been successful selling to

Your job is now to create lots of little documents that act as your current source of truth.

That’s where your “taste” lives, that’s your direction, and it’ll only keep working if you keep them current, because a source of truth that’s stale won’t work for you.

I’ve built maybe a dozen skills on top of this base over the last few months. Account research, account qualification, a pricing advisory workflow, an AEO content engine, a de-slopper that strips the AI smell out of my own writing (I fall into traps too!).

They got useful the moment they had a foundation to read from, because each one by itself didn’t make a big difference for me.

I want to share the key ingredients, then I’ll show you how to structure this for your own business.

The overarching system

I’ll explain the different bits in this system, so let’s start with positioning

Buckets

People love putting tools in buckets. Before you write a word of content you’ve already made a positioning bet, and there are only three of them (

Fletch PMM has the cleanest version of this

).

Put yourself in a bucket

everyone already knows

and say why you’re different. CRM, e-signature, data warehouse, ERP.

The budget exists, people shop for it, you educate nobody. The problem is the shelf is owned. Salesforce and HubSpot already have the space, and you fight for a spot on the shortlist with real differentiation or a distribution edge, or you’re done-for.

Put yourself in a bucket

only a small group knows

and carry it to people who’ve never heard of it.

A greenfield with fewer public fights with competitors but you haul the whole education burden door to door. You also unfortunately have to carry the category’s reputation, both good or bad.

I’m thinking about AI SDRs here 👀

Say you’re a

brand new bucket

you invented. You get to design the job to be done and the size of the problem.

You also get to learn that the first mover rarely wins the category they created (Vrbo before Airbnb, AltaVista before Google, etc.), and that the market might refuse your label and keep calling you the old thing anyway.

The reason you have to do this first is because it has a massive downstream impact.

Your bucket decides who you compete with, where your differentiation lives, what your wedge is, and what your content needs to be:

In a mature category, you write comparisons and battlecards.

vs

If you invented category, you write education and a manifesto.

So even the same product would have completely different GTM.

I don’t think this should be abstract, because it quite rightly changes what your content skill is even allowed to do. I know lots of founders and marketers who kind of forget to make that declaration (or explain it to their AI), so the skill picks one for them and it usually picks wrong.

For what it’s worth, Solvimon is running strategy 3 (headless monetization) for most AI startups, but also strategy 1 vs Stripe for more established customers. My previous company Paid ran strategy 3 too for agentic monetization.

I’ll say plainly because it’s partly a category grab, and more following a move others already started than leading it.

But you can’t write the ICP, the messaging, or a single post until you’ve picked one of the three. So start here and make it count!

The doc this produces:

positioning-strategy.md

You're my positioning strategist - a relentless interviewer whose job is to extract the basics of my positioning and how I see the world. Your goal is to create a comprehensive document that captures my unique positioning so precisely that another LLM could produce content uniquely designed for my positioning

<interview_philosophy>
You’re not here to be polite. You’re here to get to the truth. Most people can’t articulate their positioning — they give vague, socially acceptable answers. Your job is to break through that.
</interview_philosophy>

<interview_rules>

1. ONE question at a time. Wait for my response before moving on.

2. Push back on vague answers. If I say “My product is suitable for everyone” ask “How is that true? Give me an example of a simple customer, vs a more professional one.”

3. Ask for specific examples. “Show me how your product does this.”

4. Call out contradictions. If I said one thing earlier and something different now, point it out.

5. Go deeper on interesting threads. If something unusual emerges, follow it.

6. Don’t accept “I don’t know” easily. Try reframing the question or approaching from another angle.

</interview_rules>

My product does.... [one paragraph].

My top 3 competitors: [names + URLs].

Who buys today: [notes].

There are only three positioning strategies: (1) compete in a mature
category buyers already shop for, (2) take an immature category to people
who've never heard of it, (3) create a new category from scratch.

Tell me which one fits, the trade-off I'm accepting, who I'd compete with,
and what content that implies. Then draft positioning-strategy.md: the
bucket I'm choosing, why, and what I'm explicitly choosing NOT to be.

OK but who are you selling to?

The willingness to pay, the segment, and the jobs people hire you for are the unglamorous bits that you have to internalise. Many founders swear they’ve done it, but it’s very rarely machine-readable.

Give this a shot: Open a blank page and write out your ICP as cleanly as you can. Now imagine you’ve hired a new SDR, would they be able to figure out who’s in and who’s out? If you couldn’t make it understandable, the AI you’re asking for content won’t either and it’ll invent (meaning, hallucinate) new stuff that’s just wrong.

Garbage in, garbage out….

Building a skill is the “easy” part, the judgement you build in front of it is harder and that’s what you need to do first.

The doc this produces:

icp.md

(then your account-research and qualification skills will read it)

You're my ICP analyst - a relentless interviewer whose job is to pin down exactly who I sell to, who I don't, and why. Your goal is a document so precise another LLM could qualify a cold list of accounts with it and reach the same answers I would.

<interview_philosophy>
Founders describe their ICP the way they wish it were, not the way it is. Your job is to separate the accounts that actually close and renew from the ones I just like talking to. Push until the profile is specific enough to exclude someone.
</interview_philosophy>

<interview_rules>
1. ONE question at a time. Wait for my answer.
2. Reject "everyone" and "any company that needs X." Make me name the last 5 deals that actually closed.
3. Make me name disqualifiers, not just qualifiers. Who should I never sell to?
4. Separate the buyer, the user, and the budget holder. These are personas, often different people, and they come after the ICP is defined.
5. Turn fuzzy signals into observable ones. "Growing fast" becomes "posted 3+ eng roles this quarter."
6. Tag every claim verified / inferred / estimated. If it's not in my inputs, write "not available."
</interview_rules>

Read positioning-strategy.md first.
My inputs: [paste 3-5 customer interview transcripts or call notes].
My 10 best closed-won accounts: [list].
My worst-fit / churned accounts: [list].

When you've extracted enough, draft icp.md: who's in, who's out, hard
disqualifiers, the buyer/user/budget split, and 3-5 observable timing signals.

Keep a log of what you learn

Knowledge rots and gets old.

At a seed-stage startup, it can change multiple times a monthe, or even as frequently as new leads come in within a day.

The ICP you define now will be only partially right in 90 days and you need to figure out what changed.

Examples include a new competitor, a new word that a buyer is using, or a segment you ignored suddenly appear in your inbound.

If you simply overwrite stuff, you lose the context for your worldview.

So keep it dated and sequential.

Every new thing I learn lands in a timestamped file (010626-win-loss.md, that kind of thing), but sometimes I get lazy and I dump everything in one recent-stuff.md)

You ideally want a short-term memory file for “what changed since last time,” a long-term one for the milestones so that new sessions read from those and get your most recent knowledge.

I skip this a bit sometimes because it feels like admin but I’m getting better at doing it because it does make a big difference between a system that learns and improves and outdated stuff.

The docs this produces:

latest.md

(set aside 20m a week to do this with Wisprflow)

You're my memory keeper. Your job is to keep my source-of-truth files current so no signal gets lost and nothing quietly goes stale.

<routine>
1. Read latest.md first, so you know the current state.
2. Take what I learned this week: [paste the new signal, call note, competitor move].
3. Decide where it belongs. Append a dated entry (DDMMYY-topic) to the right foundation file.
4. Update latest.md with a one-line "what changed since last time."
5. Log anything milestone-worthy.
6. Tell me which downstream files this should make me re-check, and why.
</routine>

If the new signal contradicts something already on file, flag the contradiction instead of overwriting it.

Don’t lie

I’d rather you have nothing than write something that’s wrong.

Build the distrust in and tag every claim.

Separate your assumptions, axioms, and verifiable facts.

If you have sources, include a URL and a date next to them. Don’t make up numbers that sound plausible because again the downstream effects can be damaging.

My account research skill is under standing orders to say “limited information available for this account” rather than making up fiction that seems plausible – because it will do that if you don’t tell it to.

I know this feels paranoid – “what’s the harm?” you’re asking…

I feel like if it survives you skim-reading it, then your inputs lie, everything downstream lies with them, faster and in your own brand voice, which is about the worst way I can think of to be wrong at scale… And customers pick up on that.

Paste this rule into every research skill you build:

<anti_hallucination_rules>
- Tag every claim: verified (with source URL + date), inferred, estimated, or not available.
- Never invent numbers, customers, or quotes. If it's not in the inputs, write "not available."
- Prefer a short honest gap over a smooth confident paragraph.
- When you're inferring, say so out loud and show the reasoning, so I can overrule you.
</anti_hallucination_rules>

Write down how you sound, including what you’d never say

The other foundation is brand – in terms of voice (not a logo and colors)

I have a file that describes how I write down to the tics. It also has a long list of things I will never do: no em dashes, no “it’s not X, it’s Y” reframes, no “thoughts?” at the end of a post, no fake-vulnerability, no calling anything a game-changer.

You should have one of these yourself, and

you can lean on this stop-slop skill to start with

.

Telling a model what good looks like gets you 70% and telling it exactly what to never do gets you the other 20% because the AI tells are predictable and you can typically name them. The other 10% – is on you!

That voice file is what my content engine and my content-pillars skill both read before they write a word. And then everything I draft gets run through the de-slopper, which is basically that “never do” list turned into an editor. I draft fast and loose with AI on purpose (volume is part of the game), then I let the de-slopper hunt down the slop. Draft like a machine, edit like a human who’s allergic to machines. Not my favourite admission, but it’s how the sausage gets made.

The bonus: once the brand lives in a file, it stops drifting. A founder posts Monday, an agent posts Tuesday, and without a written voice they slowly converge on the same beige LinkedIn cadence everyone else uses. With one, Tuesday still sounds like you.

The doc this produces:

voice.md

(read by every writing skill)

You're my voice analyst. Your job is to reverse-engineer how I write so precisely that another LLM could draft a post and I'd believe I wrote it.

<rules>
1. Work only from real samples I give you. Don't invent a voice you think I should have.
2. Capture the mechanics: sentence rhythm, paragraph length, the words I reach for, the structure I default to.
3. Capture the negative space: a "never do" list of my AI tells and banned phrases, specific enough to catch a violation.
4. Where you're unsure, ask me for another sample instead of guessing.
</rules>

Here are 5-10 things I've written that sound most like me: [paste].

Draft voice.md in two halves: how I sound, and what I'd never write.

And the de-slop pass, run on every draft (including the AI’s own):

Read voice.md. Edit this draft to match it and strip every AI tell on the
never-do list. Return the cleaned draft, then a short changelog of what you
cut and why. Don't add ideas, don't change my meaning.

Then, and only then, the skills

Here’s the order that actually works, and it’s the opposite of how most people do it.

Foundation first:

ICP

jobs to be done

a dated learning log

a written brand and voice.

That’s weeks of unsexy work and it’s the whole game. Skills come after that, and a skill is literally your judgement written down so it doesn’t have to live in your head and go away when you’re on holiday.

My pricing advisory skill isn’t magic: it’s common questions I’d ask anyone on a call It’s the questions I’d ask on a real call, typically in the order I’d ask them in… I encoded the way I think once, and now it runs without me. That’s the whole thing, and notice it required me to know how I think first.

Take account research as the simplest case. With a real ICP sitting upstream, the skill pulls a company, scores it against who you actually sell to, and hands you a brief that says “fits the scaling-fintech profile, hiring billing engineers, Stripe already in the stack, here’s the angle.” Without the ICP, the exact same skill hands you a competent Wikipedia summary that helps you with precisely nothing. The mechanics are identical. The judgment underneath is the entire difference, and the judgment is the part you have to do by hand.

If you build the skills before the foundation, you get a very fast intern with amnesia and no taste. If you build the foundation first, the skills inherit your taste for free.

Prompt to turn most repeated task into a skill:

You're my skill designer. Your job is to turn a task I do well by hand into a reusable skill that another LLM (or future me) can run without losing my judgment.

<rules>
1. Interview me until you understand the task, my exact steps, and the one rule I never break.
2. Make me name what good output looks like, with a real example.
3. Pin down what the skill reads (which foundation files) and what it writes (the output artifact, and where it lands).
4. If a step relies on taste I haven't written down, stop and tell me which foundation file is missing.
</rules>

The task: [describe it].
The way I do it well, in order: [your steps].
The one rule I never break: [the principle].

Output the skill, including the example of good output and an explicit
reads-from / writes-to.

What this looks like for you

You don’t need

my

skills for marketing, but you do need the layer underneath them, which is portable to any GTM job.

Reminder:

Write your ICP so a stranger could qualify accounts with it.

Write your positioning so the difference (not the “better,” the difference) survives without you in the room.

Start a dated log and actually add to it when you learn something.

Write your voice down, especially the parts that are about what you’d never say.

at that point the skills almost build themselves, because a skill is just “take this judgment I already wrote down and apply it 100 times without complaining”…

I put together a spec sheet of the skills worth building…. But if you only do one thing, do the boring part because that’s what people tend to neglect.

The boring part is the part that will set you apart.

Get the spec sheet here
