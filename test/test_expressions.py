from braid_triggers.expressions import eval_expressions

test_case = {"expressions": {"val.=": "b if b else 'default'"}, "names": {"b": "here"}}


def test_expression_eval():
    res = eval_expressions(**test_case)
    print(f"DEBUG  (res):= {(res)}")
