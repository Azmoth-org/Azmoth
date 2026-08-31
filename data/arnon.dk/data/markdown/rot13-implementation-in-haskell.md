# Rot13 implementation in Haskell

- **URL:** https://arnon.dk/rot13-implementation-in-haskell/
- **Author:** Arnon Shimoni
- **Published:** 2014-10-10T23:32:08+00:00
- **Modified:** 2014-11-15T15:04:40+00:00
- **Type:** post
- **Topics:** haskell
- **Tags:** haskell, rot13
- **Reading time:** 1 minute
- **Description:** Rot13 is a simple Caeser-cypher where letters are replaced by shifting them by 13 places. > import Data.Maybe (fromMaybe) > rot13 :: String -> String > rot13 s = map rotchar s > where we'll first look in the lowercase letters > rotchar c = case (lookup c $ transp lc) of > Just x […]

Rot13 is a simple Caeser-cypher where letters are replaced by shifting them by 13 places.

> import Data.Maybe (fromMaybe)

> rot13 :: String -> String
> rot13 s = map rotchar s
>  where

we'll first look in the lowercase letters

>   rotchar c = case (lookup c $ transp lc) of
>     Just x -> x -- success! replace letter

if we can't find anything in the lowercase letters, we'll have a look in the uppercase letters.
if that fails, we'll keep the symbol as is

>     Nothing -> fromMaybe c (lookup c $ transp uc) -- Nothing means we failed... lookup in upper case letters, or leave letter as is

transp will generate a lookup list, containing a tuple of an original letter and the transposed variant [('a','n'),('b','o')...]

>   transp x = zip x ((drop 13 x) ++ (take 13 x))
>   lc = ['a' .. 'z']
>   uc = ['A' .. 'Z'] -- could also replace with map toUpper lc, but requires importing Data.Char

This implementation respects the case of the letters, and keeps special symbols as is…

ghci> :l rot13.lhs
[1 of 1] Compiling Main             ( rot13.lhs, interpreted )
Ok, modules loaded: Main.
ghci> rot13 "floof"
"sybbs"
ghci> rot13 "!Plunk~"
"!Cyhax~"
ghci> rot13 "Cyhax!"
"Plunk!"
