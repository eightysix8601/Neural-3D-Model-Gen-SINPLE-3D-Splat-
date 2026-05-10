code = open('/opt/SuGaR/sugar_scene/sugar_model.py').read()
old = '''def _knn_points_torch(points, points2=None, lengths1=None, lengths2=None, K=16, **kwargs):
    """pytorch3d knn_points 호환 구현"""
    import torch
    p = points[0] if points.dim() == 3 else points
    K = kwargs.get('K', K)
    diff = p.unsqueeze(0) - p.unsqueeze(1)
    dist2 = (diff ** 2).sum(-1)
    topk = torch.topk(dist2, k=min(K+1, dist2.shape[1]), dim=1, largest=False)
    dists = topk.values[:, 1:]
    idx   = topk.indices[:, 1:]
    class KNNResult:
        def __init__(self, dists, idx):
            self.dists = dists.unsqueeze(0)
            self.idx   = idx.unsqueeze(0)
    return KNNResult(dists, idx)'''
new = '''def _knn_points_torch(points, points2=None, lengths1=None, lengths2=None, K=16, **kwargs):
    """pytorch3d knn_points 호환 구현 - 배치 처리로 메모리 절약"""
    import torch
    p = points[0] if points.dim() == 3 else points
    N = p.shape[0]
    batch_size = 4096
    all_dists = []
    all_idx = []
    for i in range(0, N, batch_size):
        batch = p[i:i+batch_size]
        diff = batch.unsqueeze(1) - p.unsqueeze(0)
        dist2 = (diff ** 2).sum(-1)
        k = min(K+1, N)
        topk = torch.topk(dist2, k=k, dim=1, largest=False)
        d = topk.values[:, 1:]
        idx = topk.indices[:, 1:]
        all_dists.append(d)
        all_idx.append(idx)
    dists = torch.cat(all_dists, dim=0)
    idx = torch.cat(all_idx, dim=0)
    class KNNResult:
        def __init__(self, dists, idx):
            self.dists = dists.unsqueeze(0)
            self.idx   = idx.unsqueeze(0)
    return KNNResult(dists, idx)'''
code = code.replace(old, new)
open('/opt/SuGaR/sugar_scene/sugar_model.py', 'w').write(code)
print('완료!')
