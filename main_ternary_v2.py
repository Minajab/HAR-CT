#!/usr/bin/python

import os
import torch
import torch.nn as nn
import numpy as np
from model import get_model_to_quantify, device, get_model_full
# from data import train_loader, test_loader
import data_preprocess
from quantification import quantize, get_quantization_grads
import test_and_val as test
import sys, getopt


def get_model(dataset_name, kernel_size=3, model_type='ternary'):
    if dataset_name == 'uci_har':
        num_features = 9
        num_classes = 6
        num_timesteps = 128
        name_prefix = 'uci_har'

    elif dataset_name == 'motion_sense':
        num_features = 12
        num_classes = 6
        num_timesteps = 50
        name_prefix = 'motion_sense'
    else:
        raise Exception("Sorry, dataset could not be found!")
    if 'ternary' in model_type:
        return get_model_to_quantify(n_timesteps=num_timesteps, n_classes=num_classes,
                                     name_prefix=name_prefix,
                                     num_features=num_features,
                                     kernel_size=kernel_size)
    else:
        return get_model_full(n_timesteps=num_timesteps, n_classes=num_classes, name_prefix=name_prefix,
                              num_features=num_features, kernel_size=kernel_size)


def run_project(argv):
    try:
        opts, args = getopt.getopt(argv, "hd:k:", ["dataset=", "kernel="])
    except getopt.GetoptError:
        print('test.py -d <dataset> -k <kernel>')
        sys.exit(2)
    datasets = []
    kernels = []
    # kernels = [9, 11]
    # datasets = ['uci_har', 'motion_sense']
    for opt, arg in opts:
        if opt == '-h':
            print('test.py -d <dataset> -k <kernel>')
            sys.exit()
        elif opt in ("-d", "--dataset"):
            datasets = [arg]
        elif opt in ("-k", "--kernel"):
            kernels = [int(arg)]
    best_idx = {
        'uci_har': {
            9: 0,
            11: 1,
        },
        'motion_sense': {
            9: 1,
            11: 0,
        }
    }

    for dataset_name in datasets:
        BATCH_SIZE = 32
        # train_loader, test_loader = data_preprocess.load(batch_size=BATCH_SIZE)
        train_loader, test_loader = data_preprocess.load(batch_size=BATCH_SIZE, dataset=dataset_name)
        for kernel_size in kernels:

            torch.cuda.empty_cache()
            idx_float = best_idx[dataset_name][kernel_size]
            idx_ter = 2
            # kernel_size = 7

            # dataset_name = 'motion_sense'
            # dataset_name = 'uci_har'
            # postfix = 'motion_sense_drop25_all'
            # postfix = f'{dataset_name}_drop25_all_epoch300'
            prefix = f'{dataset_name}_kernel_{kernel_size}_all_epoch300'
            float_model_prefix = f'{prefix}_{idx_float}'
            postfix = f'{prefix}_{idx_ter}'
            matrices_acc_file_name = f"logs/ternary_model_acc_{postfix}.txt"
            log_file_name = f"logs/ternary_model_log_{postfix}.txt"

            criterion = nn.CrossEntropyLoss()
            model_to_quantify = None
            model_to_quantify = get_model(dataset_name, model_type='ternary', kernel_size=kernel_size)

            # load model with full precision trained weights
            dirname = os.path.dirname(__file__)
            dirname = os.path.join(dirname, 'weights')
            weightname = os.path.join(dirname, f'{float_model_prefix}_float.ckpt')
            model_to_quantify.load_state_dict(torch.load(weightname, map_location='cpu'))

            # create a list of parameters that need to be quantized

            layer_name = '.1'
            bn_weights = [param for name, param in model_to_quantify.named_parameters() if layer_name in name]
            names = [name for name, param in model_to_quantify.named_parameters() if layer_name in name]

            weights_to_be_quantized = [param for name, param in model_to_quantify.named_parameters() if
                                       not layer_name in name]


            # store a full precision copy of parameters that need to be quantized
            full_precision_copies = [param.data.clone().requires_grad_().to(device) for param in
                                     weights_to_be_quantized]

            # for each parameter to be quantized, create a trainable tensor of scaling factors (w_p and w_n)
            scaling_factors = [torch.ones(2, requires_grad=True).to(device) for _ in
                               range(len(weights_to_be_quantized))]

            scaling_factors = [torch.full_like(scaling_factors[i], 1.0, requires_grad=True).to(device) for i in
                               range(len(weights_to_be_quantized))]

            # create optimizers for different parameter groups

            # optimizer for the networks parameters containing quantized and batch norm weights
            lr = 0.001

            # optimizers for full precision and scaling factors
            optimizer_full_precision_weights = torch.optim.Adam(full_precision_copies, lr=lr)
            optimizer_scaling_factors = torch.optim.Adam(scaling_factors, lr=lr)

            torch.set_default_tensor_type('torch.DoubleTensor')
            assert full_precision_copies[0].requires_grad is True
            assert len(weights_to_be_quantized) == len(scaling_factors)
            assert len(weights_to_be_quantized) == len(full_precision_copies)

            max_acc = 0.02
            decay_idx = 0
            num_epochs = 20

            for lr in [1e-7, 1e-8, 1e-9, 1e-10, 1e-10]:  # [1e-5, 1e-6, 1e-7, 1e-8, 1e-9, 1e-10, 1e-10]:
                optimizer_main = torch.optim.Adam([{'params': bn_weights}, {'params': weights_to_be_quantized}], lr=lr)
                # optimizers for full precision and scaling factors
                optimizer_full_precision_weights = torch.optim.Adam(full_precision_copies, lr=lr)
                optimizer_scaling_factors = torch.optim.Adam(scaling_factors, lr=lr)

                decay_idx += 1
                for epoch in range(num_epochs):
                    total_step = len(train_loader)
                    for i, (images, labels) in enumerate(train_loader):
                        # quantize weights from full precision weights
                        for index, weight in enumerate(weights_to_be_quantized):
                            w_p, w_n = scaling_factors[index]
                            weight.data = quantize(full_precision_copies[index].data, w_p, w_n)
                        # forward pass
                        images = images.to(device)
                        labels = labels.to(device)
                        labels = torch.max(labels, 1)[1]

                        model_to_quantify = model_to_quantify.float()
                        outputs = model_to_quantify(images.float())

                        loss = criterion(outputs, labels)

                        # backward pass - calculate gradients
                        optimizer_main.zero_grad()
                        optimizer_full_precision_weights.zero_grad()
                        optimizer_scaling_factors.zero_grad()
                        loss.backward()

                        for index, weight in enumerate(weights_to_be_quantized):
                            w_p, w_n = scaling_factors[index]
                            full_precision_data = full_precision_copies[index].data
                            full_precision_grad, w_p_grad, w_n_grad = get_quantization_grads(weight.grad.data,
                                                                                             full_precision_data,
                                                                                             w_p.item(),
                                                                                             w_n.item())
                            full_precision_copies[index].grad = full_precision_grad.to(device)
                            scaling_factors[index].grad = torch.FloatTensor([w_p_grad, w_n_grad]).to(device)
                            weight.grad.data.zero_()

                        if (i + 1) % total_step == 0 and epoch % 2 == 0:
                            train_loss = test.validation_loss(model_to_quantify, train_loader, criterion)
                            val_loss = test.validation_loss(model_to_quantify, test_loader, criterion)
                            epoch_idx = num_epochs * (decay_idx - 1) + epoch


                            with open(log_file_name, "a") as metrics_handle:
                                # json.dump({"epoch": epoch, "loss": self.losses, "val_loss": self.val_losses}, f)
                                metrics_handle.write(f'Epoch [{epoch_idx}/{num_epochs}], Step [{i + 1}/{total_step}], '
                                                     f'lr: {lr:.5f}, train_loss: {train_loss.item():.6f}, val_loss: {val_loss.item():.6f}\n')
                            max_acc = test.validation_acc(model_to_quantify, train_loader, test_loader, max_acc,
                                                          epoch_idx,
                                                          matrices_acc_file_name, model_name=f'{postfix}_ternary')


                        model_to_quantify = model_to_quantify.double()
                        optimizer_main.step()
                        optimizer_full_precision_weights.step()
                        optimizer_scaling_factors.step()

            print(scaling_factors)


if __name__ == '__main__':
    run_project(sys.argv[1:])
