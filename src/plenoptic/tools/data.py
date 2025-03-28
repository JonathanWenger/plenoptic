from glob import glob
from typing import List, Optional, Union, Tuple
import warnings

import imageio
import numpy as np
import os.path as op
from pyrtools import synthetic_images
from skimage import color
import torch
from torch import Tensor

from .signal import rescale

DATA_PATH = op.join(op.dirname(op.realpath(__file__)), "..", "..", "data/256")

NUMPY_TO_TORCH_TYPES = {
    bool: torch.bool,  # np.bool deprecated in fav of built-in
    np.uint8: torch.uint8,
    np.int8: torch.int8,
    np.int16: torch.int16,
    np.int32: torch.int32,
    np.int64: torch.int64,
    np.float16: torch.float16,
    np.float32: torch.float32,
    np.float64: torch.float64,
    np.complex64: torch.complex64,
    np.complex128: torch.complex128,
}

TORCH_TO_NUMPY_TYPES = {value: key for (key, value) in NUMPY_TO_TORCH_TYPES.items()}


def to_numpy(x: Union[Tensor, np.ndarray], squeeze: bool = False) -> np.ndarray:
    r"""cast tensor to numpy in the most conservative way possible

    Parameters
    ----------
    x
        Tensor to be converted to `numpy.ndarray` on CPU.

    squeeze
        Removes all dummy dimensions of the tensor

    Returns
    -------
    Converted tensor as `numpy.ndarray` on CPU.
    """

    try:
        x = x.detach().cpu().numpy().astype(TORCH_TO_NUMPY_TYPES[x.dtype])
    except AttributeError:
        # in this case, it's already a numpy array
        pass
    if squeeze:
        x = x.squeeze()
    return x


def load_images(paths: Union[str, List[str]], as_gray: bool = True) -> Tensor:
    r"""Correctly load in images

    Our models and synthesis methods expect their inputs to be 4d
    float32 images: (batch, channel, height, width), where the batch
    dimension contains multiple images and channel contains something
    like RGB or color channel. This function helps you get your inputs
    into that format. It accepts either a single file, a list of files,
    or a single directory containing images, will load them in,
    normalize them to lie between 0 and 1, convert them to float32,
    optionally convert them to grayscale, make them tensors, and get
    them into the right shape.

    Parameters
    ----------
    paths
        A str or list of strs. If a list, must contain paths of image
        files. If a str, can either be the path of a single image file
        or of a single directory. If a directory, we try to load every
        file it contains (using imageio.imwrite) and skip those we
        cannot (thus, for efficiency you should not point this to a
        directory with lots of non-image files). This is NOT recursive.
    as_gray
        Whether to convert the images into grayscale or not after
        loading them. If False, we do nothing. If True, we call
        skimage.color.rgb2gray on them.

    Returns
    -------
    images
        4d tensor containing the images.
    """
    if isinstance(paths, str):
        if op.isfile(paths):
            paths = [paths]
        elif op.isdir(paths):
            paths = glob(op.join(paths, "*"))
        else:
            raise Exception(
                "paths must either a single file, a list of "
                "files, or a single directory, unsure what "
                "to do with %s!" % paths
            )
    images = []
    for p in paths:
        try:
            im = imageio.imread(p)
        except ValueError:
            warnings.warn(
                f"Unable to load in file {p}, it's probably not "
                "an image, skipping..."
            )
            continue
        # make it a float32 array with values between 0 and 1
        im = im / np.iinfo(im.dtype).max
        if im.ndim > 2:
            if as_gray:
                # From scikit-image 0.19 on, it will treat 2d signals as 1d
                # images with 3 channels, so only call rgb2gray when it's more
                # than 2d
                try:
                    im = color.rgb2gray(im)
                except ValueError:
                    # then maybe this is an rgba image instead
                    im = color.rgb2gray(color.rgba2rgb(im))
            else:
                # RGB(A) dimension ends up on the last one, so we rearrange
                im = np.moveaxis(im, -1, 0)
        elif im.ndim == 2 and not as_gray:
            # then expand this grayscale image to the rgb representation
            im = np.expand_dims(im, 0).repeat(3, 0)
        images.append(im)
    if len(set([i.shape for i in images])) > 1:
        raise ValueError("All images must be the same shape but got the following: "
                         f"{[i.shape for i in images]}")
    images = torch.tensor(np.array(images), dtype=torch.float32)
    if as_gray:
        if images.ndimension() != 3:
            raise ValueError(
                "For loading in images as grayscale, this should be a 3d tensor!"
            )
        images = images.unsqueeze(1)
    else:
        if images.ndimension() == 3:
            # either this was a single color image or multiple grayscale ones
            if len(paths) > 1:
                # then single color image, so add the batch dimension
                images = images.unsqueeze(0)
            else:
                # then multiple grayscales ones, so add channel dimension
                images = images.unsqueeze(1)
    if images.ndimension() != 4:
        raise ValueError(
            "Somehow ended up with other than 4 dimensions! Not sure how we got here"
        )
    return images


def convert_float_to_int(im: np.ndarray, dtype=np.uint8) -> np.ndarray:
    r"""Convert image from float to 8 or 16 bit image

    We work with float images that lie between 0 and 1, but for saving
    them (either as png or in a numpy array), we want to convert them to
    8 or 16 bit integers. This function does that by multiplying it by
    the max value for the target dtype (255 for 8 bit 65535 for 16 bit)
    and then converting it to the proper type.

    We'll raise an exception if the max is higher than 1, in which case
    we have no idea what to do.

    Parameters
    ----------
    im
        The image to convert
    dtype
        The target data type.  {np.uint8, np.uint16}

    Returns
    -------
    im
        The converted image, now with dtype=dtype
    """
    if im.max() > 1:
        raise Exception(
            f"all values of im must lie between 0 and 1, but max is {im.max()}"
        )
    return (im * np.iinfo(dtype).max).astype(dtype)


def make_synthetic_stimuli(size: int = 256, requires_grad: bool = True) -> Tensor:
    r"""Make a set of basic stimuli, useful for developping and debugging models

    Parameters
    ----------
    size
        The stimuli will have `torch.Size([size, size])`.
    requires_grad
        Whether to initialize the simuli with gradients.

    Returns
    -------
    stimuli
        Tensor of shape [11, 1, size, size]. The set of basic stiuli:
        [impulse, step_edge, ramp, bar, curv_edge, sine_grating, square_grating,
        polar_angle, angular_sine, zone_plate, fractal]
    """

    impulse = np.zeros((size, size))
    impulse[size // 2, size // 2] = 1

    step_edge = synthetic_images.square_wave(
        size=size, period=size + 1, direction=0, amplitude=1, phase=0
    )

    ramp = synthetic_images.ramp(size=size, direction=np.pi / 2, slope=1)

    bar = np.zeros((size, size))
    bar[
        size // 2 - size // 10 : size // 2 + size // 10, size // 2 - 1 : size // 2 + 1
    ] = 1

    curv_edge = synthetic_images.disk(size=size, radius=size / 1.2, origin=(size, size))

    sine_grating = synthetic_images.sine(size) * synthetic_images.gaussian(
        size, covariance=size
    )

    square_grating = synthetic_images.square_wave(
        size, frequency=(0.5, 0.5), phase=2 * np.pi / 3.0
    )
    square_grating *= synthetic_images.gaussian(size, covariance=size)

    polar_angle = synthetic_images.polar_angle(size)

    angular_sine = synthetic_images.angular_sine(size, 6)

    zone_plate = synthetic_images.zone_plate(size)

    fract = synthetic_images.pink_noise(size, fract_dim=0.8)

    stim = [
        impulse,
        step_edge,
        ramp,
        bar,
        curv_edge,
        sine_grating,
        square_grating,
        polar_angle,
        angular_sine,
        zone_plate,
        fract,
    ]
    stim = [rescale(s) for s in stim]

    stimuli = torch.cat(
        [
            torch.tensor(s, dtype=torch.float32, requires_grad=requires_grad)
            .unsqueeze(0)
            .unsqueeze(0)
            for s in stim
        ],
        dim=0,
    )

    return stimuli


def polar_radius(
    size: Union[int, Tuple[int, int]],
    exponent: float = 1.0,
    origin: Optional[Union[int, Tuple[int, int]]] = None,
    device: Optional[Union[str, torch.device]] = None,
) -> Tensor:
    """Make distance-from-origin (r) matrix

    Compute a matrix of given size containing samples of a radial ramp
    function, raised to given exponent, centered at given origin.

    Parameters
    ----------
    size
        If an int, we assume the image should be of dimensions `(size,
        size)`. if a tuple, must be a 2-tuple of ints specifying the
        dimensions.
    exponent
        The exponent of the radial ramp function.
    origin
        The center of the image. if an int, we assume the origin is at
        `(origin, origin)`. if a tuple, must be a 2-tuple of ints
        specifying the origin (where `(0, 0)` is the upper left).  if
        None, we assume the origin lies at the center of the matrix,
        `(size+1)/2`.
    device
        The device to create this tensor on.

    Returns
    -------
    res
        The polar radius matrix.
    """
    if not hasattr(size, "__iter__"):
        size = (size, size)

    if origin is None:
        origin = ((size[0] + 1) / 2.0, (size[1] + 1) / 2.0)
    elif not hasattr(origin, "__iter__"):
        origin = (origin, origin)

    # for some reason, torch.meshgrid returns them in the opposite order
    # that np.meshgrid does. So, in order to get the same output, we
    # grab them as (yramp, xramp) instead of (xramp, yramp). similarly,
    # we have to reverse the order from (size[1], size[0]) to (size[0],
    # size[1])
    yramp, xramp = torch.meshgrid(
        torch.arange(1, size[0] + 1, device=device) - origin[0],
        torch.arange(1, size[1] + 1, device=device) - origin[1],
    )

    if exponent <= 0:
        # zero to a negative exponent raises:
        # ZeroDivisionError: 0.0 cannot be raised to a negative power
        r = xramp**2 + yramp**2
        res = np.power(r, exponent / 2.0, where=(r != 0))
    else:
        res = (xramp**2 + yramp**2) ** (exponent / 2.0)
    return res


def polar_angle(
    size: Union[int, Tuple[int, int]],
    phase: float = 0.0,
    origin: Optional[Union[int, Tuple[float, float]]] = None,
    device: Optional[torch.device] = None,
) -> Tensor:
    """Make polar angle matrix (in radians).

    Compute a matrix of given size containing samples of the polar angle (in radians, CW from the
    X-axis, ranging from -pi to pi), relative to given phase, about the given origin pixel.

    Parameters
    ----------
    size
        If an int, we assume the image should be of dimensions `(size, size)`. if a tuple, must be
        a 2-tuple of ints specifying the dimensions
    phase
        The phase of the polar angle function (in radians, clockwise from the X-axis)
    origin
        The center of the image. if an int, we assume the origin is at `(origin, origin)`. if a
        tuple, must be a 2-tuple of ints specifying the origin (where `(0, 0)` is the upper left).
        if None, we assume the origin lies at the center of the matrix, `(size+1)/2`.
    device
        The device to create this tensor on.

    Returns
    -------
    res
        The polar angle matrix
    """
    if not hasattr(size, "__iter__"):
        size = (size, size)

    if origin is None:
        origin = ((size[0] + 1) / 2.0, (size[1] + 1) / 2.0)
    elif not hasattr(origin, "__iter__"):
        origin = (origin, origin)

    # for some reason, torch.meshgrid returns them in the opposite order
    # that np.meshgrid does. So, in order to get the same output, we
    # grab them as (yramp, xramp) instead of (xramp, yramp). similarly,
    # we have to reverse the order from (size[1], size[0]) to (size[0],
    # size[1])
    yramp, xramp = torch.meshgrid(
        torch.arange(1, size[0] + 1, device=device) - origin[0],
        torch.arange(1, size[1] + 1, device=device) - origin[1],
    )

    res = torch.atan2(yramp, xramp)

    res = ((res + (np.pi - phase)) % (2 * np.pi)) - np.pi

    return res


def _find_min_int(vals):
    """Find the minimum non-negative int not in an iterable.

    Parameters
    ----------
    vals : iterable
        iterable of ints or iterables of ints

    Returns
    -------
    min_idx : int
        minimum non-negative int

    """
    flat_vals = []
    for v in vals:
        try:
            flat_vals.extend(v)
        except TypeError:
            flat_vals.append(v)
    flat_vals = set(flat_vals)
    try:
        poss_vals = set(np.arange(max(flat_vals) + 1))
    except ValueError:
        # then this is empty sequence and thus we should return 0
        return 0
    try:
        min_int = min(poss_vals - flat_vals)
    except ValueError:
        min_int = max(flat_vals) + 1
    return min_int
