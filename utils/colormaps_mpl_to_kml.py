#%%
import matplotlib.cm as cm
import numpy as np

colormap = cm.get_cmap('jet') # or any other one
n_values = 50

rgba = [colormap(x) for x in np.linspace(0, 1, n_values)]
abgr = [(c[3], c[2], c[1], c[0]) for c in rgba]

hex_abgr = ['"#{:02X}{:02X}{:02X}{:02X}"'.format(*[int(255*x) for x in c]) for c in abgr]
print("[" + ", ".join(hex_abgr) + "]")