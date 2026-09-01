part = work_part
exprs = part.Expressions
count = 0
for expr in exprs:
    count += 1
print(f"Total expressions: {count}")
for i, expr in enumerate(exprs):
    print(f"  {i}: Name={expr.Name}, Value={expr.ExpressionValue}")