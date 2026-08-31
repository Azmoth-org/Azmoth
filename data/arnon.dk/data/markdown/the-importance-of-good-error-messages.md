# How do you write good error messages?

- **URL:** https://arnon.dk/the-importance-of-good-error-messages/
- **Author:** Arnon Shimoni
- **Published:** 2015-03-09T21:33:41+00:00
- **Modified:** 2019-08-16T14:44:04+00:00
- **Type:** post
- **Topics:** Talks
- **Tags:** error, good error messages, how to write error messages, messages, start up, ux
- **Reading time:** 4 minutes
- **Description:** Developing software in a start up has exposed me to some pretty bad error messages. Back when the company had little to no customers, this wasn’t a big deal. However, our recent influx of new customers requires a little more attention in curating proper error messages. I gathered all of our developers and we did […]

Developing software in a start up has exposed me to some pretty bad error messages.

Back when the company had little to no customers, this wasn’t a big deal. However, our recent influx of new customers requires a little more attention in curating proper error messages.

I gathered all of our developers and we did a short session about how to write proper error messages.

First, a little background – we separate our error messages into two classes:

Standard error messages, to be seen by the user – with an additional stack trace and information to help a developer pinpoint the problem

Internal error messages, seen only by the developer.

Theoretically speaking, a user should never need to see an internal error message. In reality though, this sometimes happens – but not because of bad code, but rather misuse of the internal error message system.

Examples of bad error messages

Most products are chock full of unhelpful error messages.

Sometimes the errors can be unhelpful or even confusing.

When we were developing our product, we wrote error messages for our own use mostly.

Today, customers are actually paying for our product, so we should actually attempt to help them instead of piss them off.

Why do we even bother with error messages?

There are two well known laws in computer software development:

Users don’t read documentation.

Users will read system documentation only when they are in trouble.

Users will listen to your error messages when they’re keen on solving the error and recovering.

Error messages can and should teach users a bit about how the system works and help them solve the problem they’re facing.

If the error message doesn’t help, we might as well get rid of it altogether.

How do you write good error messages?

Established wisdom holds that good error messages are polite, precise, and constructive.

I personally think that a good error message should also reduce time and work necessary to recover, and help the user learn more about the system.

A good error message should let the user know:

That an error has occurred

Why the error occurred

How to recover if possible

That it isn’t fatal, hopefully

The Four Hs

Adapted from

Ben Rowe’s

The 4 H’s of Writing Error Messages

Human

There’s nothing more frustrating than an error that reads like “Error – Unauthorized” or “Error – invalid uint8_t”. It sounds like it has been written by a robot, for a robot.

You should attempt to write your error message as if you were conversing with your user about the error, while keeping it as friendly and jargon-free as possible.

When writing the error, imagine someone asking you about the error and what it means. You should write that down -that’s your error message.

Helpful

Does the message explain clearly what went wrong?

Your error message needs to explain the problem as clearly as possible,

and it needs to be specific.

A vague error message that says, “Internal Consistency Check Failed” is just lazy programming. It’s of no use to anyone.

And most importantly …

Does it help the user recover?

What do they need to do next? How can they get back to what they were doing, as fast as possible?

Humerous

A short sprinkling of humour is often a great way to diffuse the frustration of an error. Keeping your tone light-hearted can help to keep the user on-side. Because we are a start up, humourous error messages are tolerated!

Take care though, because there is a fine line between humourous and annoying.

Think about how severe the error is

, because if its a simple validation issue, the user will be able to take the joke.

If we accidentally dropped the entire database however, being cute is most inappropriate.

Humble

There is a chance that the error has occurred due to a flaw in our system. It’s always better to assume that

our product is at fault, not the user

.

Your error message must

never

imply that the user made a mistake (even if they did). They

will

be paying our salaries.

To summarize it all up

Always write the error message from the user’s point of view and using the user’s vocabulary.

Consider the error “If this is a server-side error, contact System Administration.” How will the user tell if this was a server-side error or not?

Be descriptive

When possible, describe system impact

Offer pointers for debugging

Write error messages as though they’ll be read by someone who’s tired, pissed off, and has no idea how the code in question works.

Because eventually, the person reading that error message will be you.
