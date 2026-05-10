code = open('/opt/SuGaR/sugar_scene/sugar_model.py').read()
old = 'def _knn_points_torch(points, K=16, **kwargs):'
new = 'def _knn_points_torch(points, points2=None, lengths1=None, lengths2=None, K=16, **kwargs):'
code = code.replace(old, new)
old2 = '    p = points[0]  # (N, 3)'
new2 = '    p = points[0] if points.dim() == 3 else points'
code = code.replace(old2, new2)
open('/opt/SuGaR/sugar_scene/sugar_model.py', 'w').write(code)
print('완료!')
