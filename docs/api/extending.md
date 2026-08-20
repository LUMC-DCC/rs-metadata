# Extension points

A new metadata format is an `Adapter` plus a crosswalk mapping. [Recipes](../developing/recipes.md) has the order to do it in.

```{eval-rst}
.. automodule:: rs_metadata.adapters.base
   :members: Adapter, SourceError
```

```{eval-rst}
.. automodule:: rs_metadata.adapters.registry
   :members: ADAPTERS, ANCHOR, companion_adapters, get_adapter
```

```{eval-rst}
.. automodule:: rs_metadata.mapping
   :members: Mapping, FieldRule, Rule, load, available
```

