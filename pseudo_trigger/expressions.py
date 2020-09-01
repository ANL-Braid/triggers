from typing import Any, Dict, Mapping

from simpleeval import EvalWithCompoundTypes, InvalidExpression


def eval_expressions(
    expressions: Mapping[str, Any],
    names: Mapping[str, Any],
) -> Dict[str, Any]:

    errors = []
    evaluator = EvalWithCompoundTypes()
    result_params = {}
    for key, val in expressions.items():
        # We'll only need to process string type keys that end with the magic .=
        if not (isinstance(key, str) and key.endswith(".=")):
            # If this key isn't an expression, but the value is a dict itself, we recurse
            # and evaluate there as well
            if isinstance(val, dict):
                val = eval_expressions(val, names)
            # Or, if the value is a list, check each of the entries
            elif isinstance(val, list):
                new_vals = []
                for item in val:
                    if isinstance(item, dict):
                        item = eval_expressions(item, names)
                    new_vals.append(item)
                val = new_vals
            result_params[key] = val
            continue
        short_key = key[:-2]  # strip off the '.=' suffix
        try:
            evaluator.names = names
            val = evaluator.eval(val)
            result_params[short_key] = val
        except TypeError as te:
            error_msg = (
                f"TypeError '{str(te)} when evaluating expression "
                f"({val}) for Parameter {key}"
            )
            errors.append(error_msg)
        except InvalidExpression as ie:
            error_msg = (
                f"InvalidExpression '{str(ie)} when evaluating expression "
                f"({val}) for Parameter {key}"
            )
            errors.append(error_msg)
        except SyntaxError as se:
            error_msg = (
                f"Invalid Syntax on expression ({val}) "
                f"occurred at position {se.offset} for Parameter {key}"
            )
            errors.append(error_msg)
    if len(errors) > 0:
        raise ValueError(";".join(errors))
    return result_params
