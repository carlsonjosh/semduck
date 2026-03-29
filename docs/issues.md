# Potential Issues to Explore

## Are metrics compiling from facts?
I found one semduck nuance while testing: named metrics compile against physical table expressions, not previously declared facts.
  That means helper facts like item_count_value don’t get substituted inside metric definitions, so I’m simplifying the view to define
  the metrics directly on the underlying columns.