"""Dump a Mesh-TensorFlow T5/mT5 checkpoint (TensorBundle format) to a .npz file.

Runs in a TensorFlow-only environment; the PyTorch side (convert_mt5_npz_to_hf.py)
needs no TensorFlow. Adafactor slot variables are skipped.

Usage: python dump_tf_checkpoint.py <ckpt_prefix> <out.npz>
"""
import json
import sys

import numpy as np
import tensorflow as tf

ckpt, out = sys.argv[1], sys.argv[2]
reader = tf.train.load_checkpoint(ckpt)
shapes = reader.get_variable_to_shape_map()
dtypes = reader.get_variable_to_dtype_map()
arrays, meta = {}, {}
for name in sorted(shapes):
    if "_slot_" in name or name in ("global_step",) or name.startswith("step"):
        continue
    arr = reader.get_tensor(name)
    # bfloat16 (ml_dtypes) has no numpy equivalent: cast to float32 here so the
    # PyTorch side never needs TensorFlow or ml_dtypes.
    arrays[name.replace("/", "__")] = np.asarray(arr).astype(np.float32)
    meta[name] = {"shape": list(shapes[name]), "dtype": str(dtypes[name])}
np.savez(out, **arrays)
json.dump(meta, open(out + ".meta.json", "w"), indent=1)
print(f"dumped {len(arrays)} tensors -> {out}; skipped {len(shapes)-len(arrays)} slot/step vars")
total = sum(int(np.prod(v["shape"])) for v in meta.values())
print(f"total parameters: {total:,}")
for n, m in list(meta.items())[:12]:
    print(" ", n, m["shape"], m["dtype"])
