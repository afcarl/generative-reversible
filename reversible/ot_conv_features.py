import torch as th
from reversible.sliced import sample_directions, norm_and_var_directions


def standardize_by_outs(this_all_outs, wanted_all_outs):
    standardized_l_out = []
    standardized_l_wanted = []
    for i_layer in range(len(this_all_outs)):
        l_out = this_all_outs[i_layer]
        l_reshaped = l_out.transpose(1,0).contiguous().view(l_out.size()[1], -1)
        means = th.mean(l_reshaped, dim=1)
        stds = th.std(l_reshaped, dim=1)
        mean_std = th.mean(stds)
        l_standardized = (l_reshaped - means.unsqueeze(1)) / mean_std
        l_standardized = l_standardized.transpose(1,0).contiguous().view(*l_out.size())
        standardized_l_out.append(l_standardized)
        l_wanted_out = wanted_all_outs[i_layer]
        l_wanted_reshaped = l_wanted_out.transpose(1,0).contiguous().view(l_wanted_out.size()[1], -1)
        l_wanted_standardized = (l_wanted_reshaped - means.unsqueeze(1)) / mean_std
        l_wanted_standardized = l_wanted_standardized.contiguous().view(*l_wanted_out.size())
        standardized_l_wanted.append(l_wanted_standardized)
    return standardized_l_out, standardized_l_wanted


def sliced_loss_for_dirs_3d(samples_full_a, samples_full_b, directions, diff_fn):
    proj_a = th.matmul(samples_full_a, directions.t())
    proj_b = th.matmul(samples_full_b, directions.t())
    sorted_a, _ = th.sort(proj_a, dim=1)
    sorted_b, _ = th.sort(proj_b, dim=1)
    # sorted are examples x locations x dirs
    n_a = len(sorted_a)
    n_b = len(sorted_b)
    if n_a > n_b:
        assert n_a % n_b == 0
        increase_factor = n_a // n_b
        sorted_a = sorted_a.view(n_a // increase_factor,
                                 increase_factor,
                                 sorted_a.size()[1],
                                 sorted_a.size()[2])
        sorted_b = sorted_b.unsqueeze(1)
    elif n_a < n_b:
        assert n_b % n_a == 0
        increase_factor = n_b // n_a
        sorted_b = sorted_b.view(n_b // increase_factor,
                                 increase_factor,
                                 sorted_b.size()[1],
                                 sorted_b.size()[2])
        sorted_a = sorted_a.unsqueeze(1)

    if diff_fn == 'w2':
        eps = 1e-6
        loss = th.sqrt(th.mean((sorted_a - sorted_b) ** 2) + eps)
    elif diff_fn == 'sqw2':
        loss = th.mean((sorted_a - sorted_b) ** 2)
    return loss


def layer_sliced_loss(this_all_outs, wanted_all_outs, return_all=False, orthogonalize=True,
                    adv_dirs=None,
                      diff_fn='w2',
                      n_dirs=1):
    layer_losses = []
    for i_layer in range(len(this_all_outs)):
        layer_outs = this_all_outs[i_layer]
        layer_wanted_outs = wanted_all_outs[i_layer]
        all_dirs = [sample_directions(n_dims=layer_outs.size()[1], orthogonalize=orthogonalize, cuda=True)
                    for _ in range(n_dirs)]
        directions = th.cat(all_dirs)
        if adv_dirs is not None:
            this_adv_dirs = norm_and_var_directions(adv_dirs[i_layer])
            directions = th.cat((directions, this_adv_dirs), dim=0)
        samples_full_a = layer_outs.contiguous().view(layer_outs.size()[0], layer_outs.size()[1], -1).permute(0,2,1)
        samples_full_b = layer_wanted_outs.contiguous().view(
            layer_wanted_outs.size()[0],
            layer_wanted_outs.size()[1],
            -1).permute(0,2,1)
        layer_loss = sliced_loss_for_dirs_3d(samples_full_a, samples_full_b, directions, diff_fn=diff_fn)
        layer_losses.append(layer_loss)
    if return_all:
        return th.cat(layer_losses, dim=0)
    else:
        total_loss = th.mean(th.cat(layer_losses, dim=0))
        return total_loss

def to_one_out_per_layer(l_outs):
    reshaped_l_outs = [l_out.transpose(1, 0).unsqueeze(0) for l_out in
                       l_outs]
    return reshaped_l_outs


def pixels_to_batch(l_out):
    return l_out.transpose(0,1).contiguous().view(l_out.size()[1], -1).transpose(0,1)


def choose(pixels, n_max):
    if len(pixels) > n_max:
        inds = th.randperm(len(pixels))[:n_max].cuda()
        return pixels[inds]
    else:
        return pixels