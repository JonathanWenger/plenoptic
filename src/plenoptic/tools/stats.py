from typing import List, Optional, Union

import torch
from torch import Tensor


def variance(
    x: Tensor,
    mean: Optional[Tensor] = None,
    dim: Optional[Union[int, List[int]]] = None,
    keepdim: bool = False,
) -> Tensor:
    r"""sample estimate of `x` *variability*

    Parameters
    ----------
    x
        The input tensor
    mean
        Reuse a precomputed mean
    dim
        The dimension or dimensions to reduce.
    keepdim
        Whether the output tensor has dim retained or not.

    Returns
    -------
    out
        The variance tensor.
    """
    if dim is None:
        dim = tuple(range(x.ndim))
    if mean is None:
        mean = torch.mean(x, dim=dim, keepdim=True)
    return torch.mean((x - mean).pow(2), dim=dim, keepdim=keepdim)


def skew(
    x: Tensor,
    mean: Optional[Tensor] = None,
    var: Optional[Tensor] = None,
    dim: Optional[Union[int, List[int]]] = None,
    keepdim: bool = False,
) -> Tensor:
    r"""Sample estimate of `x` *asymmetry* about its mean

    Parameters
    ----------
    x
        The input tensor
    mean
        Reuse a precomputed mean
    var
        Reuse a precomputed variance
    dim
        The dimension or dimensions to reduce.
    keepdim
        Whether the output tensor has dim retained or not.

    Returns
    -------
    out
        The skewness tensor.
    """
    if dim is None:
        dim = tuple(range(x.ndim))
    if mean is None:
        mean = torch.mean(x, dim=dim, keepdim=True)
    if var is None:
        var = variance(x, mean=mean, dim=dim, keepdim=keepdim)
    return torch.mean((x - mean).pow(3), dim=dim, keepdim=keepdim) / var.pow(1.5)


def kurtosis(
    x: Tensor,
    mean: Optional[Tensor] = None,
    var: Optional[Tensor] = None,
    dim: Optional[Union[int, List[int]]] = None,
    keepdim: bool = False,
) -> Tensor:
    r"""sample estimate of `x` *tailedness* (presence of outliers)

    kurtosis of univariate noral is 3.

    smaller than 3: *platykurtic* (eg. uniform distribution)

    greater than 3: *leptokurtic* (eg. Laplace distribution)

    Parameters
    ----------
    x
        The input tensor.
    mean
        Reuse a precomputed mean.
    var
        Reuse a precomputed variance.
    dim
        The dimension or dimensions to reduce.
    keepdim
        Whether the output tensor has dim retained or not.

    Returns
    -------
    out
        The kurtosis tensor.
    """
    if dim is None:
        dim = tuple(range(x.ndim))
    if mean is None:
        mean = torch.mean(x, dim=dim, keepdim=True)
    if var is None:
        var = variance(x, mean=mean, dim=dim, keepdim=keepdim)
    return torch.mean(torch.abs(x - mean).pow(4), dim=dim, keepdim=keepdim) / var.pow(2)
