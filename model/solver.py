# -*- coding: utf-8 -*-
import math

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import os
import random
import json
import h5py
from tqdm import tqdm, trange
from layers.summarizer import PGL_SUM
from utils import TensorboardWriter


class Similarity(nn.Module):
    """
    Dot product or cosine similarity
    """

    def __init__(self, temp):
        super().__init__()
        self.temp = temp
        self.cos = nn.CosineSimilarity(dim=-1)

    def forward(self, x, y):
        return self.cos(x, y) / self.temp


class Solver(object):
    def __init__(self, config=None, train_loader=None, test_loader=None):
        """Class that Builds, Trains and Evaluates PGL-SUM model"""
        # Initialize variables to None, to be safe
        self.model, self.optimizer, self.writer = None, None, None

        self.config = config
        self.train_loader = train_loader
        self.test_loader = test_loader

        # Set the seed for generating reproducible random numbers
        if self.config.seed is not None:
            torch.manual_seed(self.config.seed)
            torch.cuda.manual_seed_all(self.config.seed)
            np.random.seed(self.config.seed)
            random.seed(self.config.seed)

    def build(self):
        """ Function for constructing the PGL-SUM model of its key modules and parameters."""
        # Model creation
        self.model = PGL_SUM(input_size=self.config.input_size,
                             output_size=self.config.input_size,
                             num_segments=self.config.n_segments,
                             heads=self.config.heads,
                             fusion=self.config.fusion,
                             pos_enc=self.config.pos_enc).to(self.config.device)
        if self.config.init_type is not None:
            self.init_weights(self.model, init_type=self.config.init_type, init_gain=self.config.init_gain)

        if self.config.mode == 'train':
            # Optimizer initialization
            self.optimizer = optim.Adam(self.model.parameters(), lr=self.config.lr, weight_decay=self.config.l2_req)
            self.writer = TensorboardWriter(str(self.config.log_dir))

    @staticmethod
    def init_weights(net, init_type="xavier", init_gain=1.4142):
        """ Initialize 'net' network weights, based on the chosen 'init_type' and 'init_gain'.

        :param nn.Module net: Network to be initialized.
        :param str init_type: Name of initialization method: normal | xavier | kaiming | orthogonal.
        :param float init_gain: Scaling factor for normal.
        """
        for name, param in net.named_parameters():
            if 'weight' in name and "norm" not in name:
                if init_type == "normal":
                    nn.init.normal_(param, mean=0.0, std=init_gain)
                elif init_type == "xavier":
                    nn.init.xavier_uniform_(param, gain=np.sqrt(2.0))  # ReLU activation function
                elif init_type == "kaiming":
                    nn.init.kaiming_uniform_(param, mode="fan_in", nonlinearity="relu")
                elif init_type == "orthogonal":
                    nn.init.orthogonal_(param, gain=np.sqrt(2.0))      # ReLU activation function
                else:
                    raise NotImplementedError(f"initialization method {init_type} is not implemented.")
            elif 'bias' in name:
                nn.init.constant_(param, 0.1)

    criterion = nn.CosineSimilarity(dim=1, eps=1e-6)
    cos_sim = Similarity(temp=0.1)
    # criterion = nn.MSELoss()
    loss_fct = nn.CrossEntropyLoss()  # reduction='none'

    def reconstruction_loss(self, video_embedding, attentive_ft):

        return torch.norm(video_embedding - attentive_ft, p=2)
    def variance_loss(self, scores, epsilon=1e-4):
        median_tensor = torch.zeros(scores.shape[1]).to("cuda")
        median_tensor.fill_(torch.median(scores))
        loss = nn.MSELoss()
        variance = loss(scores.squeeze(), median_tensor)
        return 1 / (variance + epsilon)

    def train(self):
        """ Main function to train the PGL-SUM model. """
        if self.config.verbose:
            tqdm.write('Time to train the model...')

        for epoch_i in trange(self.config.n_epochs, desc='Epoch', ncols=80):
            self.model.train()

            loss_history = []
            recon_loss_history = []
            eucl_dist_history = []
            num_batches = int(len(self.train_loader) / self.config.batch_size)  # full-batch or mini batch
            iterator = iter(self.train_loader)
            for _ in trange(num_batches, desc='Batch', ncols=80, leave=False):
                self.optimizer.zero_grad()
                embeddings = []
                mean_similarity_list = []
                h = []
                h1 = []
                h2 = []
                for _ in trange(self.config.batch_size, desc='Video', ncols=80, leave=False):
                    frame_features = next(iterator)

                    frame_features = frame_features.to(self.config.device)
                    # frame_features_cap = frame_features_cap.to(self.config.device)
                    # target = target.to(self.config.device)

                    '''
                    for k in range(2):
                        output, weights = self.model(frame_features.squeeze(0), frame_features_cap.squeeze(0))
                        h.append(output)
                        
                    '''
                    output, weights = self.model(frame_features.squeeze(0))
                    h1.append(output)
                    output, weights = self.model(frame_features.squeeze(0))
                    h2.append(output)
                    '''
                    output_1, weights_1 = self.model(frame_features.squeeze(0), frame_features_cap.squeeze(0))
                    h.append(output_1)
                    output_2, weights_2 = self.model(frame_features.squeeze(0), frame_features_cap.squeeze(0))
                    h.append(output_2)
                    output_3, weights_3 = self.model(frame_features.squeeze(0), frame_features_cap.squeeze(0))
                    h.append(output_3)
                    output_4, weights_4 = self.model(frame_features.squeeze(0), frame_features_cap.squeeze(0))
                    h.append(output_4)
                    '''
                # h_4 = torch.stack(h, dim=0).squeeze(1)  #.detach().cpu().numpy()

                h1 = torch.stack(h1, dim=0).squeeze(1)
                h2 = torch.stack(h2, dim=0).squeeze(1)


                '''
                    cos_sim_matrix = self.cos_sim(h.unsqueeze(1), h.unsqueeze(0)).detach().cpu().numpy()
                    np.fill_diagonal(cos_sim_matrix, 0)
                    mean_similarity = cos_sim_matrix.sum() / 12
                    mean_similarity_list.append(mean_similarity)
                '''

                # cos_sim_matrix = self.cos_sim(h_4.unsqueeze(1), h_4.unsqueeze(0)).unsqueeze(0)  #.detach().cpu().numpy()

                cos_sim_matrix = self.cos_sim(h1.unsqueeze(1), h2.unsqueeze(0)).unsqueeze(0)  #.detach().cpu().numpy()

                # np.fill_diagonal(cos_sim_matrix, 0)
                # M, N = cos_sim_matrix.shape
                # K = 4
                # L = 4
                # MK = M // K
                # NL = N // L
                # cos_sim_matrix_avg = cos_sim_matrix[:MK*K, :NL*L].reshape(MK, K, NL, L).mean(axis=(1, 3))
                # cos_sim_matrix_avg = torch.Tensor(cos_sim_matrix_avg).to('cuda')
                # cos_sim_matrix_avg.requires_grad = True
                '''
                avg_pooling = nn.AvgPool2d(2)
                cos_sim_matrix_avg = avg_pooling(cos_sim_matrix).squeeze(0)
                '''
                labels = torch.arange(cos_sim_matrix.size(1)).long().to("cuda")   # cos_sim_matrix_avg.size(0)
                cos_sim_matrix = cos_sim_matrix.squeeze(0)
                '''
                for i in trange(self.config.batch_size, desc='Video', ncols=80, leave=False):
                    pos_pair = torch.exp(cos_sim_matrix_avg[i, i]).to(self.config.device)
                    neg_pairs = 0
                    for j in range(self.config.batch_size):
                        if i != j:
                            neg_pair = torch.exp(cos_sim_matrix_avg[i, j]).to(self.config.device)
                            neg_pairs = neg_pairs + neg_pair

                    loss = -1 * torch.log(pos_pair / neg_pairs).to(self.config.device)
                    '''
                loss = self.loss_fct(cos_sim_matrix, labels)   # cos_sim_matrix_avg

                # for i in range(self.config.batch_size):
                    # loss = losses[i]
                if self.config.verbose:
                    tqdm.write(f'[{epoch_i}] loss: {loss.item()}')
                loss.backward()
                loss_history.append(loss.data)
                # Update model parameters every 'batch_size' iterations
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.clip)
                self.optimizer.step()

            # Mean loss of each training step
            loss = torch.stack(loss_history).mean()
            # reconstruction_loss = torch.stack(recon_loss_history).mean()
            # euclidean_distance = torch.stack(eucl_dist_history).mean()

            # Plot
            if self.config.verbose:
                tqdm.write('Plotting...')

            self.writer.update_loss(loss, epoch_i, 'total_loss_epoch')
            # self.writer.update_loss(reconstruction_loss, epoch_i, 'reconstruction_loss_epoch')
            # self.writer.update_loss(euclidean_distance, epoch_i, 'euclidean_distance_epoch')
            # self.writer.update_losses({'total_loss_epoch': loss, 'reconstruction_loss_epoch': reconstruction_loss, 'euclidean_distance_epoch': euclidean_distance}, epoch_i, 'All_losses')

            # Uncomment to save parameters at checkpoint
            if not os.path.exists(self.config.save_dir):
                os.makedirs(self.config.save_dir)
            # ckpt_path = str(self.config.save_dir) + f'/epoch-{epoch_i}.pkl'
            # tqdm.write(f'Save parameters at {ckpt_path}')
            # torch.save(self.model.state_dict(), ckpt_path)

            self.evaluate(epoch_i)

    def evaluate(self, epoch_i, save_weights=False):
        """ Saves the frame's importance scores for the test videos in json format.

        :param int epoch_i: The current training epoch.
        :param bool save_weights: Optionally, the user can choose to save the attention weights in a (large) h5 file.
        """
        self.model.eval()

        weights_save_path = self.config.score_dir.joinpath("weights.h5")
        out_scores_dict = {}
        for frame_features, video_name in tqdm(self.test_loader, desc='Evaluate', ncols=80, leave=False):
            # [seq_len, input_size]
            frame_features = frame_features.view(-1, self.config.input_size).to(self.config.device)
            # frame_features_cap = frame_features_cap.to(self.config.device)

            with torch.no_grad():
                video_embedding, attn_weights = self.model(frame_features)  # [1, seq_len]
                # scores = scores.squeeze(0).cpu().numpy().tolist()
                attn_weights = attn_weights.cpu().numpy().tolist()

                out_scores_dict[video_name] = attn_weights

            if not os.path.exists(self.config.score_dir):
                os.makedirs(self.config.score_dir)

            scores_save_path = self.config.score_dir.joinpath(f"{self.config.video_type}_{epoch_i}.json")
            with open(scores_save_path, 'w') as f:
                if self.config.verbose:
                    tqdm.write(f'Saving score at {str(scores_save_path)}.')
                json.dump(out_scores_dict, f)
            scores_save_path.chmod(0o777)

            if save_weights:
                with h5py.File(weights_save_path, 'a') as weights:
                    weights.create_dataset(f"{video_name}/epoch_{epoch_i}", data=attn_weights)


if __name__ == '__main__':
    pass