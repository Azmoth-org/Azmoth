# Your DBMS is slow. What do you do?

- **URL:** https://arnon.dk/your-dbms-is-slow-what-do-you-do/
- **Author:** Arnon Shimoni
- **Published:** 2020-04-28T17:36:21+00:00
- **Modified:** 2020-09-03T15:24:45+00:00
- **Type:** post
- **Topics:** Uncategorized
- **Reading time:** 5 minutes
- **Description:** I first used SQL for an online blogging platform I was building in Perl back in 1999. Moving from a flat-file to MySQL was truly a lifechanging experience. The (then) four-year-old DBMS had a nice little set of features and optimizations that I could easily apply and get a decent performance boost. Call me a […]

I first used SQL for an online blogging platform I was building in Perl back in 1999. Moving from a flat-file to MySQL was truly a lifechanging experience. The (then) four-year-old DBMS had a nice little set of features and optimizations that I could easily apply and get a decent performance boost.

Call me a masochist, but I quite like spending a few hours or days determining why a query is slow – because the reward of solving it and speeding it up by an order of magnitude is amazing.

The landscape has changed quite a bit since however, but the challenges mostly remain. Some common optimizations can speed up a query by 10x, but overusing optimizations can actually slow them down, or cause big problems when you scale to more data or more substantial workloads.

In the rest of this post, I’ll detail some common tasks and ideas for solving (or working around) common SQL issues.

Common causes of SQL performance issues

Tech debt in schemas

–

Often, bad schema design can slow down queries. Excessively wide datatypes such as VARCHARs to store numbers are common culprits.

Legacy data warehousing strategies

–

Many legacy strategies like cubes and pre-aggregated tables may be hiding numerous levels of complexities, including nested views.

Poor indexing strategies

–

Not indexing enough or indexing too much can both have the same outcome – slow queries and high disk-space usage.

Incorrectly configured servers

–

Each server has its own best practices for optimizing CPU, kernel, and networking both at the BIOS level and at the operating system level. Not following these recommendations could result in ~20% slower queries.

Underpowered hardware or under-provisioned instances

–

Even if you don’t manage your own database, having an underpowered or outdated server running your DBMS can cost you in performance.

Improve performance of existing systems

Here are some things to try when your queries are slow, without changing your servers or instances:

Let the database engine do as much of the work as possible

Most DBMSs handle data very efficiently — much more efficiently than a client application:

A wealth of functionality in text processing, math, summarization, and sorting are best left for DBMSs, rather than in applications

Moving some logic from the application to the DBMS ensures re-usability across applications and users

Minimize I/O of data to and from the database

With very big queries, strain can come from transmitting result sets to the client. Do you really need

all the data?

If not, reduce the result set size in the DBMS:

Pull out the names only of the columns you need instead of using

SELECT *

. Otherwise, if you have a very wide table, the

client

may struggle putting it all together

Unless you need to see every row, limit the result set size with

LIMIT

Break complex queries into smaller queries

Large queries can be hard to work out. Breaking queries into small bits and using

temporary tables

can make the query much more understandable.

Temporary tables and small queries are easier to debug – often eliminatingthe need for exotic syntax

Temporary tables are less sensitive to failing because the query optimizer decides to do things differently

Temporary tables and small queries give you a chance to optimize yourself. Sometimes this is better than stuff the DBMS optimizer hasn’t figured out itself

Prefer optimized functions, limit wildcards

Vendor-written functions often outperform SQL functions chained together.

Some examples:

With lots of Unicode text, using pattern matching (

LIKE '%foo%'

) can result in very inefficient plans. A function like

ISPREFIXOF(x,'foo')

will likely perform better

Some DBMSs (like SQream DB and Postgres) are case-sensitive. If you need to match strings, try doing it on one side only or use a case-insensitive match (

ILIKE

)

Use views carefully

Views are virtual tables that are created from a query. A view is often materialized when you run a query that accesses them.

If your query uses a view, or even your view has another view, you’re running many queries without knowing it

(This isn’t a problem in SQream DB, but with some other DBMSs, it could surprise you!)

Use temporary tables to materialize a view every hour/day/week, or as required

Consider using a

CTE

instead of a view.

Check your indexing strategy

In many DBMSs, indexes speed up your query, letting the DBMS know where to look for data. Apply indices selectively – focus on columns with high cardinality or columns you use often.

Too many indices decrease write performance (and take up lots of space):

Remove indices that aren’t used or are rarely used.

Remove indices that are placed on columns that have random data and/or are frequently updated

Indexing strategies affect not only performance, but also the data size. This can become a real problem when your database scales.

BRIN index data by “2ndQuadrant PostgreSQL”, tested on Postgres 9.5

Follow best practices for your DBMS

Each DBMS is different, so be sure to apply best practices for the DBMS you use.

However, there are some things that will always be true:

If one query is slow, check the best practices for query optimization

If your whole database is slow, check your system:

Cluster status – all nodes are up, open for statements

Query distribution – are all statements ending up on the same node?

Data distribution – is data not distributed correctly? Could a schema change do some good?

Deleted rows – many big data DBMSs including SQream DB, Vertica, Postgres benefit from a periodic maintenance of deleted rows (also called delete predicates, delete vectors)

Locks – check if any statements are waiting due to locks, such as when a big table is being updated

Counters – If your DBMS supports it, set up counters to track memory and compute usage

Dealing with the elephant in the room

There’s only so much you can tweak and tune. When you can’t (or won’t) tune any further, consider updating your DBMS.

New SQL DBMSs such as SQream DB:

Use modern compute resources to their fullest,

and then some

Can automate metadata collection

Have new methodologies that scale better, are less susceptible to ‘growing pains’

Allow joining any number of tables without significant performance impact

Following best practices can shave 10%-30% off query time even on mostly well-optimized workloads. Sometimes, that’s not enough.
