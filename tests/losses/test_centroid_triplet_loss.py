import unittest

import torch

from itertools import chain

from pytorch_metric_learning.distances import CosineSimilarity
from pytorch_metric_learning.losses import CentroidTripletLoss
from pytorch_metric_learning.reducers import MeanReducer
from pytorch_metric_learning.utils import common_functions as c_f

from .. import TEST_DEVICE, TEST_DTYPES

def normalize(embeddings):
    return torch.nn.functional.normalize(embeddings, p=2, dim=0)

class TestCentroidTripletLoss(unittest.TestCase):
    def test_centroid_triplet_loss(self):
        margin = 0.2
        loss_funcA = CentroidTripletLoss(margin=margin)
        loss_funcB = CentroidTripletLoss(margin=margin, reducer=MeanReducer())
        loss_funcC = CentroidTripletLoss(margin=margin, distance=CosineSimilarity())
        loss_funcD = CentroidTripletLoss(
            margin=margin, reducer=MeanReducer(), distance=CosineSimilarity()
        )
        loss_funcE = CentroidTripletLoss(margin=margin, smooth_loss=True)
        
        for dtype in TEST_DTYPES:
            per_class_angles = [
                [0, 10, 20],
                [30, 40, 50],
            ]
            centroid_makers = [
                [[10, 20], [40, 50]],
                [[0, 20], [30, 50]],
                [[0, 10], [30, 40]]
            ]
            
            embedding_angles = chain(*per_class_angles)
            embeddings = torch.tensor(
                [c_f.angle_to_coord(a) for a in embedding_angles],
                requires_grad=True,
                dtype=dtype,
            ).to(TEST_DEVICE)  # 2D embeddings
            labels = torch.LongTensor([0, 0, 0, 1, 1, 1])

            centroids = torch.tensor([
                [
                    [c_f.angle_to_coord(a) for a in coords] 
                    for coords in one_maker]
                for one_maker in centroid_makers
            ], requires_grad=True, dtype=dtype).to(TEST_DEVICE)
            centroids = centroids.sum(-2) / 2
            
            [lossA, lossB, lossC, lossD, lossE] = [
                x(embeddings, labels)
                for x in [loss_funcA, loss_funcB, loss_funcC, loss_funcD, loss_funcE]
            ]

            triplets = [
                (0, (0, 0), 3     ),
                (0, (0, 0), (0, 1)),
                (3, (0, 1), 0     ),
                (3, (0, 1), (0, 0)),

                (1, (1, 0), 4     ),
                (1, (1, 0), (1, 1)),
                (4, (1, 1), 1     ),
                (4, (1, 1), (1, 0)),
                
                (2, (2, 0), 5    ),
                (2, (2, 0), (2, 1)),
                (5, (2, 1), 2    ),
                (5, (2, 1), (2, 0)),
            ]

            correct_loss = 0
            correct_loss_cosine = 0
            correct_smooth_loss = 0
            num_non_zero_triplets = 0
            num_non_zero_triplets_cosine = 0
            
            cos_loss_col = []
            for a, pc, nc in triplets:
                anchor = embeddings[a]
                if type(pc) == int:
                    positive = embeddings[pc]
                else:
                    positive = centroids[pc[0]][pc[1]]

                if type(nc) == int:
                    negative = embeddings[nc]
                else:
                    negative = centroids[nc[0]][nc[1]]

                ap_dist = torch.sqrt(torch.sum((anchor - positive) ** 2))
                an_dist = torch.sqrt(torch.sum((anchor - negative) ** 2))
                curr_loss = torch.relu(ap_dist - an_dist + margin)
                
                curr_loss_cosine = torch.relu(
                    torch.sum(normalize(anchor) * normalize(negative)) - torch.sum(normalize(anchor) * normalize(positive)) + margin
                )
                
                cos_loss_col.append(curr_loss_cosine)

                ap_dist = torch.sqrt(torch.sum((normalize(anchor) - normalize(positive)) ** 2))
                an_dist = torch.sqrt(torch.sum((normalize(anchor) - normalize(negative)) ** 2))
                correct_smooth_loss += torch.nn.functional.softplus(
                    ap_dist - an_dist + margin
                )
                if curr_loss > 0:
                    num_non_zero_triplets += 1
                if curr_loss_cosine > 0:
                    num_non_zero_triplets_cosine += 1
                correct_loss += curr_loss
                correct_loss_cosine += curr_loss_cosine
            rtol = 1e-2 if dtype == torch.float16 else 1e-5

            
            self.assertTrue(
                torch.isclose(lossA, correct_loss / num_non_zero_triplets, rtol=rtol)
            )
            self.assertTrue(
                torch.isclose(lossB, correct_loss / len(triplets), rtol=rtol)
            )
            self.assertTrue(
                torch.isclose(
                    lossC, correct_loss_cosine / num_non_zero_triplets_cosine, rtol=rtol
                )
            )
            self.assertTrue(
                torch.isclose(lossD, correct_loss_cosine / len(triplets), rtol=rtol)
            )
            self.assertTrue(
                torch.isclose(lossE, correct_smooth_loss / len(triplets), rtol=rtol)
            )

    def test_no_allow_imbalanced(self):
        loss_funcA = CentroidTripletLoss(margin=0.2)
        loss_funcB = CentroidTripletLoss(margin=0.2, reducer=MeanReducer())
        for dtype in TEST_DTYPES:
            embedding_angles = [0, 20, 40, 60, 80]
            embeddings = torch.tensor(
                [c_f.angle_to_coord(a) for a in embedding_angles],
                requires_grad=True,
                dtype=dtype,
            ).to(
                TEST_DEVICE
            )  # 2D embeddings
            labels = torch.LongTensor([0, 1, 1, 2, 2])

            with self.assertRaises(Exception):
                lossA = loss_funcA(embeddings, labels)
                lossB = loss_funcB(embeddings, labels)
    
    def test_backward(self):
        margin = 0.2
        loss_funcA = CentroidTripletLoss(margin=margin)
        loss_funcB = CentroidTripletLoss(margin=margin, reducer=MeanReducer())
        loss_funcC = CentroidTripletLoss(smooth_loss=True)
        for dtype in TEST_DTYPES:
            for loss_func in [loss_funcA, loss_funcB, loss_funcC]:
                embedding_angles = [0, 20, 40, 60, 80, 85]
                embeddings = torch.tensor(
                    [c_f.angle_to_coord(a) for a in embedding_angles],
                    requires_grad=True,
                    dtype=dtype,
                ).to(
                    TEST_DEVICE
                )  # 2D embeddings
                labels = torch.LongTensor([0, 0, 1, 1, 2, 2])

                loss = loss_func(embeddings, labels)
                loss.backward()
