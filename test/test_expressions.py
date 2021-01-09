from pseudo_trigger.expressions import eval_expressions

test_case = {"expressions": {"val.=": "b if b else 'default'"}, "names": {"b2": "here"}}


def test_expression_eval():
    res = eval_expressions(**test_case)
    print(f"DEBUG  (res):= {(res)}")
