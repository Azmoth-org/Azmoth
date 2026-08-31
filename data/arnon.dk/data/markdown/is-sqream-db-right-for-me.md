# When would SQream DB be right for me?

- **URL:** https://arnon.dk/is-sqream-db-right-for-me/
- **Author:** Arnon Shimoni
- **Published:** 2017-05-05T12:17:50+00:00
- **Modified:** 2020-09-03T15:24:47+00:00
- **Type:** post
- **Topics:** Databases, GPUs, SQream DB
- **Tags:** databases, sqream, sqream-db, sqreamdb
- **Reading time:** 3 minutes
- **Description:** I’ve been a part of SQream DB for over three years, now entering the fourth year.I started out in the core of the product – the SQL parser and compiler written in Haskell. My experience with the product started out in pure amazement at what it can do (I came from mySQL), and has evolved […]

I’ve been a part of SQream DB for over three years, now entering the fourth year.

I started out in the core of the product – the SQL parser and compiler written in Haskell.

My experience with the product started out in pure amazement at what it can do (I came from mySQL), and has evolved to a point where using any other database for big data just doesn’t satisfy me anymore.

(Honorable mention goes to memSQL for being really fun for quick and dirty in-memory stuff)

I’ve grown to appreciate SQream DB’s strengths and weaknesses, and that’s what I want to write about today.

Rethinking the clustered and distributed solutions

There are millions of projects all around the world that require relatively straight-forward analytics, but bringing them from gigabytes or terabytes into hundreds of terabytes is unfortunately not as easy.

With the typical clustered solutions that grew in popularity around the beginning of this decade, you would ‘simply add more nodes’. Unfortunately, this creates all sorts of limitations, which data scientists and BI professionals don’t appreciate.

“You can’t join these three tables, because we didn’t shard the tables for this kind of query” is all too common.

In order to keep growing, you have to rethink the solution – and GPUs are the perfect match.

By bringing thousands of cores per TESLA card, and with multiple cards per 1U, 2U or 4U host (be it x86-64 or Power8 with NVLINK), you can effectively avoid the complexities of the (now) classic distributed solution.

Cocolink Klimax 210

“Is SQream DB right for me?”

Like with any other database, the answer is

maybe.

I feel there is no one-size-fits-all in databases, and you should pick the right tool for the job.

When would SQream DB be a good fit?

If you primarily use SQL today (SQream DB is ANSI SQL compliant, with additions like window functions, regex, etc.)

If you use ODBC, JDBC, Python or .NET to query your systems

You have a schema that changes occasionally (SQream DB is columnar, so adding columns is easy)

When your queries change quite often (SQream DB does not require indexing, and transparently tags each column to pinpoint data)

When your queries are very complex and CPU-bound – many JOINs, aggregates, summarizations, regex, window functions, etc. (See

SQream’s query monster page for a tounge-in-cheek rundown

)

When you don’t want to index all of your columns, but potentially want to JOIN on any column (As above)

When you require very fast ingest of over 2TB/h (SQream DB can deal with just over 2TB/h per GPU in most situations)

When you have a footprint constraint (SQream DB will work in a GPU powered laptop, although a 2U chassis is probably better)

When would SQream DB not be a good fit?

If your data set is less than 2 TB (There are better, non-GPU solutions out there)

Your current system works well for you, and you don’t expect data to grow substantially in the future

All of your internal customers (Data scientists, BI, DBAs, etc.) are happy with the system you have right now

You’re storing and analyzing lots of binary data (The GPU doesn’t work well with binary data)

You need fulltext search capabilities on very large data types (eg. CLOBs – GPUs also don’t work well with text data)

Sub-second response times are crucial (SQream DB is designed for many terabytes on-disk, and therefore works in the seconds to minutes range)
