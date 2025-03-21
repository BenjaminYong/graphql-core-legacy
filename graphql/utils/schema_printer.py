import re

from ..language.printer import print_ast
from ..type.definition import (
    GraphQLEnumType,
    GraphQLInputObjectType,
    GraphQLInterfaceType,
    GraphQLObjectType,
    GraphQLScalarType,
    GraphQLUnionType,
)
from ..type.directives import DEFAULT_DEPRECATION_REASON
from .ast_from_value import ast_from_value


# Necessary for static type checking
if False:  # flake8: noqa
    from ..type.definition import (
        GraphQLArgument,
        GraphQLType,
        GraphQLField,
        GraphQLEnumValue,
    )
    from ..type.schema import GraphQLSchema
    from ..type.directives import GraphQLDirective
    from typing import Any, Union, Callable


MAX_DESC_LEN = 120


def print_schema(schema):
    # type: (GraphQLSchema) -> str
    return _print_filtered_schema(
        schema, lambda n: not (is_spec_directive(n)), _is_defined_type
    )


def print_introspection_schema(schema):
    # type: (GraphQLSchema) -> str
    return _print_filtered_schema(schema, is_spec_directive, _is_introspection_type)


def is_spec_directive(directive_name):
    # type: (str) -> bool
    return directive_name in ("skip", "include", "deprecated")


def _is_defined_type(typename):
    # type: (Any) -> bool
    return not _is_introspection_type(typename) and not _is_builtin_scalar(typename)


def _is_introspection_type(typename):
    # type: (str) -> bool
    return typename.startswith("__")


_builtin_scalars = frozenset(["String", "Boolean", "Int", "Float", "ID"])


def _is_builtin_scalar(typename):
    # type: (str) -> bool
    return typename in _builtin_scalars


def _print_filtered_schema(schema, directive_filter, type_filter):
    # type: (GraphQLSchema, Callable[[str], bool], Callable[[str], bool]) -> str
    return (
        "\n\n".join(
            [_print_schema_definition(schema)]
            + [
                _print_directive(directive)
                for directive in schema.get_directives()
                if directive_filter(directive.name)
            ]
            + [
                _print_type(type)
                for typename, type in sorted(schema.get_type_map().items())
                if type_filter(typename)
            ]
        )
        + "\n"
    )


def _print_schema_definition(schema):
    # type: (GraphQLSchema) -> str
    operation_types = []

    query_type = schema.get_query_type()
    if query_type:
        operation_types.append("  query: {}".format(query_type))

    mutation_type = schema.get_mutation_type()
    if mutation_type:
        operation_types.append("  mutation: {}".format(mutation_type))

    subscription_type = schema.get_subscription_type()
    if subscription_type:
        operation_types.append("  subscription: {}".format(subscription_type))

    return "schema {{\n{}\n}}".format("\n".join(operation_types))


def _print_type(type):
    # type: (GraphQLType) -> str
    if isinstance(type, GraphQLScalarType):
        return _print_scalar(type)

    elif isinstance(type, GraphQLObjectType):
        return _print_object(type)

    elif isinstance(type, GraphQLInterfaceType):
        return _print_interface(type)

    elif isinstance(type, GraphQLUnionType):
        return _print_union(type)

    elif isinstance(type, GraphQLEnumType):
        return _print_enum(type)

    assert isinstance(type, GraphQLInputObjectType)
    return _print_input_object(type)


def _print_scalar(type):
    # type: (GraphQLScalarType) -> str
    return _print_description(type) + "scalar {}".format(type.name)


def _print_object(type):
    # type: (GraphQLObjectType) -> str
    interfaces = type.interfaces
    implemented_interfaces = (
        " implements {}".format(", ".join(i.name for i in interfaces))
        if interfaces
        else ""
    )

    return ("{}type {}{} {{\n" "{}\n" "}}").format(
        _print_description(type),
        type.name,
        implemented_interfaces,
        _print_fields(type),
    )


def _print_interface(type):
    # type: (GraphQLInterfaceType) -> str
    return ("{}interface {} {{\n" "{}\n" "}}").format(
        _print_description(type),
        type.name,
        _print_fields(type),
    )


def _print_union(type):
    # type: (GraphQLUnionType) -> str
    return "{}union {} = {}".format(
        _print_description(type),
        type.name,
        " | ".join(str(t) for t in type.types),
    )


def _print_enum(type):
    # type: (GraphQLEnumType) -> str
    enum_values_str = "\n".join(
        _print_description(v, '  ', not idx) + '  ' + v.name + _print_deprecated(v)
        for idx, v in enumerate(type.values)
    )
    return ("{}enum {} {{\n" "{}\n" "}}").format(
        _print_description(type),
        type.name,
        enum_values_str,
    )


def _print_input_object(type):
    # type: (GraphQLInputObjectType) -> str
    fields_str = "\n".join(
        _print_description(f, "  ", not idx) + "  " +  _print_input_value(name, f)
        for idx, (name, f) in enumerate(type.fields.items())
    )
    return ("{}input {} {{\n" "{}\n" "}}").format(
        _print_description(type),
        type.name,
        fields_str,
    )


def _print_fields(type):
    # type: (Union[GraphQLObjectType, GraphQLInterfaceType]) -> str
    return "\n".join(
        "{}  {}{}: {}{}".format(
            _print_description(f, '  ', not idx),
            f_name,
            _print_args(f),
            f.type,
            _print_deprecated(f),
        )
        for idx, (f_name, f) in enumerate(type.fields.items())
    )


def _print_deprecated(field_or_enum_value):
    # type: (Union[GraphQLField, GraphQLEnumValue]) -> str
    reason = field_or_enum_value.deprecation_reason

    if reason is None:
        return ""
    elif reason in ("", DEFAULT_DEPRECATION_REASON):
        return " @deprecated"
    else:
        return " @deprecated(reason: {})".format(print_ast(ast_from_value(reason)))


def _print_args(field_or_directives):
    # type: (Union[GraphQLField, GraphQLDirective]) -> str
    args = field_or_directives.args

    if not args:
        return ""

    if all(not arg.description for arg in args.values()):
        return "({})".format(
            ", ".join(
                _print_input_value(arg_name, arg)
                for arg_name, arg in args.items()
            )
        )

    args_description = "\n".join(
        _print_description(arg, '  ', not idx) + "  " + _print_input_value(arg_name, arg)
        for idx, (arg_name, arg) in enumerate(args.items())
    )
    return "(\n" + args_description + "\n)"


def _print_input_value(name, arg):
    # type: (str, GraphQLArgument) -> str
    if arg.default_value is not None:
        default_value = " = " + print_ast(ast_from_value(arg.default_value, arg.type))
    else:
        default_value = ""

    return "{}: {}{}".format(name, arg.type, default_value)


def _print_directive(directive):
    # type: (GraphQLDirective) -> str
    return "{}directive @{}{} on {}".format(
        _print_description(directive),
        directive.name,
        _print_args(directive),
        " | ".join(directive.locations),
    )


def _print_description(definition, indentation="", first_in_block=True):
    if not definition.description:
        return ""

    lines = _description_lines(definition.description, MAX_DESC_LEN - len(indentation))
    if indentation and not first_in_block:
        description = "\n" + indentation + '"""'
    else:
        description = indentation + '"""'

    if len(lines) == 1 and len(lines[0]) < 70 and len(lines[0]) > 0 and lines[0][-1] != '"':
        return description + _escape_quote(lines[0]) + '"""\n'

    has_leading_space = not lines[0] or lines[0][0] in " \t"
    if not has_leading_space:
        description += "\n"

    for idx, line in enumerate(lines):
        # NOTE: This original code adds new lines for line breaks which causes JSON parsing issues.
        # if idx != 0 or not has_leading_space:
        #     description += indentation
        # description += _escape_quote(line) + "\n"
        
        description += _escape_quote(line)

    return description + indentation + '"""\n'


def _description_lines(description, max_len):
    lines = []
    if type(description) == str:
        raw_lines = description.split("\n")
    else:
        raw_lines = description().split("\n")
    for line in raw_lines:
        if line == "":
            lines.append(line)
        else:
            lines = lines + _break_lines(line, max_len)
    return lines


def _break_lines(line, max_len):
    if len(line) < max_len + 5:
        return [line]

    line_split_re = r"((?: |^).{15,%s}(?= |$))" % str(max_len - 40)
    parts = re.split(line_split_re, line)

    if len(parts) < 4:
        return [line]

    sublines = [parts[0] + parts[1] + parts[2]]
    for idx in range(3, len(parts), 2):
        sublines.append(parts[idx][1:] + parts[idx + 1])

    return sublines


def _escape_quote(line):
    return line.replace('"""', '\\"""')


__all__ = ["print_schema", "print_introspection_schema"]
