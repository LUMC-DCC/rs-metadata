# Profile checks

Each check family is a function over a `ProfileContext`, so any of them runs against a bare dictionary with no files and no pipeline. Why the rules are what they are: [Design decisions](../developing/decisions.md).

```{eval-rst}
.. automodule:: rs_metadata.profile.context
   :members: ProfileContext, flatten
```

```{eval-rst}
.. automodule:: rs_metadata.profile.runner
   :members: validate, CHECKS
```

```{eval-rst}
.. automodule:: rs_metadata.profile.types
   :members: check_types, required_form, example_for, reports_on
```

```{eval-rst}
.. automodule:: rs_metadata.profile.formats
   :members: check_formats, format_checked, valid_literal, valid_url, url_problem
```

```{eval-rst}
.. automodule:: rs_metadata.profile.jsonld
   :members: check_context, check_feature_list, check_unknown_properties
```

```{eval-rst}
.. automodule:: rs_metadata.profile.terminology
   :members: check_edam, check_vocabularies
```

```{eval-rst}
.. automodule:: rs_metadata.profile.identifiers
   :members: check_agents, check_identifiers, agent_label
```

```{eval-rst}
.. automodule:: rs_metadata.profile.licenses
   :members: check_licenses, spdx_suggestion
```

```{eval-rst}
.. automodule:: rs_metadata.profile.placeholders
   :members: check_placeholders, has_placeholder_host
```

```{eval-rst}
.. automodule:: rs_metadata.profile.recommendations
   :members: check_recommendations
```

