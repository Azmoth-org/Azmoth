# What is usage-based billing? Tokens, credits, and outcomes, explained in Simplified Technical English

- **URL:** https://arnon.dk/what-is-usage-based-billing-tokens-credits-and-outcomes-explained-in-simplified-technical-english/
- **Author:** Arnon Shimoni
- **Published:** 2026-07-19T18:46:50+00:00
- **Modified:** 2026-07-19T18:47:19+00:00
- **Type:** post
- **Topics:** billing
- **Reading time:** 8 minutes
- **Description:** What is usage-based billing? Tokens, credits, and outcomes, explained in the controlled language of aircraft manuals. The unit changes. The meter does not.

Before I begin the ASD-STE100 part, let me explain:

I’m an airplane nerd (sometimes called “Avgeek”), and I really enjoy things that have to do with aviation. Well, aircraft maintenance manuals use a controlled language known as

ASD-STE100

. From here on out, I’ll try to use the rules to write about billing.

I will disclaim however, that I used Claude to help me with adherence to the rules after I had written the post.

ASD-STE100 has approximately 900 approved words. The sentences are short. Each sentence gives one idea. The voice is active. The standard exists because an unclear sentence in a manual can kill a person.

Pages about billing have the opposite problem. The words are large and the mechanism is hidden. The reader does not know who counts what, who pays for what, or who carries the risk.

This post obeys STE.

Words such as “token” and “credit” are technical names, and the standard permits technical names. All other text follows the rules. A controlled language can describe a hydraulic system. It can also describe a rate card.

What is usage-based billing?

Usage-based billing is a model where the price follows usage. When the customer does more, the customer pays more. When the customer does less, the customer pays less.

The system has 3 parts. A meter counts events. A rate card gives a price to each event. A ledger records the charges.

The parts stay the same in each version of the model.

Only one thing changes: the unit that the meter counts.

Unit

The meter counts

Who carries the risk

Examples

Tokens

Model input and output

The customer

API pricing at OpenAI, Anthropic

Credits

Actions, converted to an abstract unit

Shared

Figma, Lovable, Cursor

Outcomes

The result of the work

The vendor

Intercom Fin, Chargeflow

This is not a standard diagram, but it is drawn to look like a schematic used in aviation maintenance.

What is a token?

A token is a small unit of text. A language model reads text as tokens and writes text as tokens. One token is approximately 4 characters of English. A short word is 1 token. A long word is 2 or 3 tokens. One page of text is approximately 500 tokens.

A tokenizer divides the text into tokens before the model starts its work. The model then writes the output one token at a time. The model provider counts the input tokens and the output tokens for each request. Output tokens usually have a higher price than input tokens.

Why are tokens important?

Tokens are the cost unit of AI. Each AI feature sends requests to a model. Each request creates a token count. The token count sets the cost of goods for the feature. Model providers set a price for each 1 million tokens. Different models have different prices.

Tokens are also the meter of AI. Electricity has the kilowatt-hour. AI has the token. A company that does not measure tokens for each customer does not know the margin for each customer. One AI company found that the top 5% of its users consumed 75% of its compute. The finance team found this at month-close, 3 months too late.

Some AI companies sell tokens to their customers at a markup. This is the simplest version of usage-based billing. The meter counts tokens. The rate card prices tokens. The invoice shows tokens.

Token pricing has a problem. The customer cannot predict the count. The customer does not know if a request costs 400 tokens or 40,000 tokens. The model decides. The bill arrives, and the customer learns the number after the fact.

Token pricing moves the cost risk to the person with the least control of it.

What is a credit?

A credit is an abstract unit that sits between the customer and the real cost. The customer buys a pool of credits before use. Each action in the product uses a set number of credits. One generated image costs 5 credits. One agent task costs 20 credits.

The vendor sets the exchange rate between credits and the cost. The customer sees the credit price. The customer does not see the token price behind it.

Credits are an architectural decision. The credit layer translates between two currencies: the cost to operate the product, and the price the customer agrees to pay.

Figma uses two types of credits. Some credits follow value. Some credits follow cost. The user decides if Gemini 3 Pro is worth 3 times the credits of a cheaper model. Figma moved that cost calculation to its customers. It is not my favourite design.

Why do credits give companies predictability?

Credits give predictability to 3 parties at the same time.

The customer gets a stable price for each action. The image costs 5 credits today. The image costs 5 credits next month. The customer can make a budget. The token count behind the image can move, and the customer does not care.

The vendor gets a stable margin structure. The vendor can change the model behind an action without a public price change. A cheaper model arrives. The vendor routes the action to it. The credit price stays the same, and the margin improves. The rate card and the cost structure become independent variables. Vercel changes its pricing 5 to 6 times in one month. A credit layer makes that speed possible.

The finance team gets a clean ledger. The customer pays for the credits before use. Revenue recognition follows usage, not the purchase. The finance team sees deferred revenue, a burn-down schedule, and a breakage number. Each of these has a known accounting treatment.

Credits also show each weakness in a v1 billing system. Stranded credits accumulate. Breakage gives profit to the vendor and removes trust from the customer. Expiry rules multiply. The companies that operate credits correctly make the credit ledger a part of their core infrastructure, not a coupon system attached to Stripe.

What is outcome-based billing?

Outcome-based billing uses the same 3 parts: a meter, a rate card, a ledger. One thing moves. The meter counts the result of the work, not the input to it.

Fin

(formerly by Intercom) charges $0.99 for each resolved support conversation. An unresolved conversation costs nothing. The tokens that Fin uses to resolve the conversation are invisible to the customer.

Justt

charges a percentage of each recovered chargeback. A lost dispute costs nothing.

The mechanism is identical to token billing. Define the event. Count the event. Price the event. Record the charge. The engineering difference is small. The commercial difference is large, because the risk moves from the customer to the vendor. The vendor now absorbs the cost of each failed attempt.

Outcome billing creates 2 new problems that token billing does not have.

Attribution. The vendor and the customer must agree on the definition of “resolved”. A customer who closes a ticket in frustration is a resolution by the meter and a failure by an honest measure. The definition of the outcome event becomes a contract term.

Verification. Someone must check the meter. Token counts come from the model provider, and nobody disputes them. Outcome counts come from the vendor, and customers dispute them. The ledger must hold the evidence for each charged event.

Why do tokens and credits need an AI-native billing system?

Subscription-era billing systems count seats. They count the seats one time each month. Token billing creates millions of events each day. The billing system must receive each event, count it, and price it in near real time. This is a different class of system.

An AI-native billing system does 5 things that a subscription system does not do:

It ingests high-volume usage events without loss. Each lost event is lost revenue, and nobody finds it.

It converts between units. Tokens become credits. Credits become invoice lines. The conversion rules live in configuration, not in custom code.

It changes rate cards without engineering work. Model providers change their prices many times in one year. The rate card must move at the same speed.

It shows the margin for each customer in real time. The month-close is too late for this number.

It keeps an audit trail for each event. Outcome billing makes the trail mandatory, because customers dispute outcome counts.

Agents add one more requirement. An agent must operate the billing system through an API or an MCP tool. A billing system that requires a human at a dashboard stops the agent. The dashboard can stay. The dashboard cannot be the only door.

Where does this go?

The progression goes in one direction. Tokens price the input. Credits price the action. Outcomes price the result. The meter, the rate card, and the ledger stay the same. Each step moves the risk nearer to the vendor.

A vendor that goes down this ladder needs one thing above all: an event ledger that survives an audit.

I am building this at Solvimon

.
