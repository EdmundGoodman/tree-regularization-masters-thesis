import os
import sys
import glob
import numpy as np
import matplotlib.pyplot as plt
import torch
import torchvision
from torch import nn
from torch.optim import Adam
from torch.utils.tensorboard import SummaryWriter
from datasets import sample_2D_data, polynom_3, polynom_6
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import confusion_matrix, ConfusionMatrixDisplay
import models
import tree_regularizer as tr
import decision_tree_utils as dtu
from torch.utils.data import DataLoader, TensorDataset
from sklearn.tree import export_graphviz
from sklearn.metrics import accuracy_score
from six import StringIO
from IPython.display import Image
from PIL import Image as ImagePIL
import pydotplus
import argparse


# todo
def scatter_plot(plot_shape, x, y, colors, title):
    pass


# todo
def train():
    pass


# todo
def test():
    pass


def decision_tree_export_graph(tree, feature_names, classes, filename):
    dot_data = StringIO()
    export_graphviz(tree, out_file=dot_data, filled=True, rounded=True, special_characters=True,
                    feature_names=feature_names,
                    class_names=classes)
    graph = pydotplus.graph_from_dot_data(dot_data.getvalue())
    graph.write_png(filename)
    Image(graph.create_png())
    img = ImagePIL.open('figures/decision_tree_reg.png')
    fig = plt.figure()
    plt.imshow(img)
    plt.close()

    return fig



def params_to_1D_vector(model_parameters):
    parameters = []
    for param in model_parameters:
        parameters.append(torch.flatten(param.data))

    return torch.cat(parameters, dim=0)


def save_data(X, Y, filename):
    file = open(filename, 'w')
    np.savetxt(file, np.hstack((X, Y.reshape(-1, 1))))

    file.close()

def colormap(Y):
    return ['b' if y == 1 else 'r' for y in Y]

def main():

    num_samples, dim, space = 500, 2, [1.5, 1.5]
    writer = SummaryWriter()

    filename = 'data.txt'

    if args.s:
        #X, Y = sample_2D_data(num_samples, polynom_3, space)
        #save_data(X, Y, filename)

        X, Y = sample_2D_data(num_samples, polynom_6, space)
        save_data(X, Y, filename)

    data_from_txt = np.loadtxt(filename)
    X = data_from_txt[:, :2]
    Y = data_from_txt[:, 2]

    X_train, X_test, y_train, y_test = train_test_split(X, Y, test_size=0.33, random_state=42)

    fig = plt.figure()
    plt.scatter(*X_train.T, c=colormap(y_train))
    plt.xlim([0, space[0]])
    plt.ylim([0, space[1]])
    plt.title('Training data')

    x_decision_fun = np.linspace(0, space[0], 100)
    y_decision_fun = polynom_3(x_decision_fun)

    plt.plot(x_decision_fun, y_decision_fun, 'k-')
    #plt.savefig('figures/samples_training_plot.png')

    #plt.show()
    writer.add_figure('Training samples', figure=fig)
    data_summary = f'Samples: {num_samples}  \nTraining data shape: {X_train.shape}  \nTest data shape: {X_test.shape}'
    writer.add_text('Training Data Summary', data_summary)

    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

    model = models.Net1(d_in=dim)
    model.to(device)

    # Hypterparameters
    num_epochs = args.ep
    batch_size = args.batch
    input_batch_size_surrogate_training = args.sb
    regularization_strength = args.rs
    learning_rate = args.lr

    # Objectives and Optimizer
    criterion = nn.MSELoss()
    criterion_tr = tr.Tree_Regularizer(regularization_strength)
    optimizer = Adam(model.parameters(), lr=learning_rate)
    surrogate_model = None
    surrogate_model_trained = False

    # Data perparation (to Tensor then create DataLoader for batch training)
    X_train = torch.tensor(X_train, dtype=torch.float32)
    y_train = torch.tensor(y_train.reshape(-1, 1), dtype=torch.float32)
    X_test = torch.tensor(X_test, dtype=torch.float32)
    y_test = torch.tensor(y_test.reshape(-1, 1), dtype=torch.float32)

    data_train = TensorDataset(X_train, y_train)
    data_train_loader = DataLoader(dataset=data_train, batch_size=batch_size)
    data_test = TensorDataset(X_test, y_test)
    data_test_loader = DataLoader(dataset=data_test, batch_size=batch_size)

    print('================Training===================')

    #num_epochs = 250
    input_data_surrogate_training = []
    APLs = []
    training_loss = []
    loss_surrogate_training = []
    # todo --> try to use PyTorch-Lightning later ...
    for epoch in range(num_epochs):
        model.train()
        running_loss = []

        if input_batch_size_surrogate_training > 0:
            for i, batch in enumerate(data_train_loader):
                x_batch, y_batch = batch[0].to(device), batch[1].to(device)

                optimizer.zero_grad()
                y_hat = model(x_batch)

                model_parameters = params_to_1D_vector(model.parameters())

                if surrogate_model_trained:
                    loss = criterion_tr(input=y_batch, target=y_hat, parameters=model_parameters, surrogate_model=surrogate_model)
                    #loss = criterion(input=y_batch, target=y_hat)
                else:
                    loss = criterion(input=y_batch, target=y_hat)

                loss.backward()
                optimizer.step()

                running_loss.append(loss.item())

            # Stack model parameters after every epoch for surrogate training
            model_parameters = params_to_1D_vector(model.parameters())
            input_data_surrogate_training.append(model_parameters)
            average_path_length = dtu.average_path_length(X_train=data_train_loader.dataset[:][0].to(device),
                                                          X_test=data_test_loader.dataset[:][0],
                                                          y_test=data_test_loader.dataset[:][1], model=model)
            APLs.append(average_path_length)

            print(f'Epoch: {epoch + 1}/{num_epochs}, loss: {np.array(running_loss).mean():.4f}')
            training_loss.append(np.array(running_loss).mean())

            input_batch_size_surrogate_training -= 1
        else:
            print('================Training surrogate model===================')
            input_data_surrogate_training = torch.vstack(input_data_surrogate_training)
            #input_data_surrogate_training = torch.zeros(size=input_data_surrogate_training.size())

            fig = plt.figure()
            plt.hist(APLs)
            plt.title(f'Histogram of APLs after epoch {epoch + 1}')
            plt.xlabel('APLs')
            writer.add_figure(f'APL Histogram/APLs Histogram after epoch: {epoch+1}', fig)
            plt.close(fig)

            APLs = torch.tensor([APLs], dtype=torch.float32).T

            surrogate_model, sr_loss = tr.train_surrogate_model(input_data_surrogate_training, APLs,
                                                                args.epsilon, learning_rate=args.lr_sr, retrain=True)
            surrogate_model_trained = True

            loss_surrogate_training.append(sr_loss)

            for i, batch in enumerate(data_train_loader):
                x_batch, y_batch = batch[0].to(device), batch[1].to(device)
                optimizer.zero_grad()
                y_hat = model(x_batch)

                model_parameters = params_to_1D_vector(model.parameters())

                loss = criterion_tr(input=y_batch, target=y_hat, parameters=model_parameters,
                                    surrogate_model=surrogate_model)
                loss.backward()
                optimizer.step()

                running_loss.append(loss.item())

            input_data_surrogate_training = []
            APLs = []

            print('================After Training surrogate model===================')
            print(f'Epoch: {epoch + 1}/{num_epochs}, loss: {np.array(running_loss).mean():.4f}')
            training_loss.append(np.array(running_loss).mean())
            input_batch_size_surrogate_training = args.sb

    for i in range(num_epochs):
        writer.add_scalar('Training Loss', training_loss[i], i)

    for i in range(len(loss_surrogate_training)):
        for j in range(len(loss_surrogate_training[i])):
            writer.add_scalar(f'Surrogate Training/Loss of surrogate training step {i}', loss_surrogate_training[i][j], j)


    print('================Test===================')
    model.eval()
    y_train_predicted = []
    y_test_predicted = []
    loss_with_train_data = []
    loss_with_test_data = []
    with torch.no_grad():
        # Test with training data
        for i, batch in enumerate(data_train_loader):
            x, y = batch[0].to(device), batch[1].to(device)
            y_hat = model(x)
            y_train_predicted.append(y_hat)

            model_parameters = params_to_1D_vector(model.parameters())

            loss = criterion_tr(input=y_hat, target=y, parameters=model_parameters, surrogate_model=surrogate_model)

            loss_with_train_data.append(loss.item())

        y_train_predicted = torch.cat(y_train_predicted)

        # Test with test data
        for i, batch in enumerate(data_test_loader):
            x, y = batch[0].to(device), batch[1].to(device)
            y_hat = model(x)
            y_test_predicted.append(y_hat)

            model_parameters = params_to_1D_vector(model.parameters())

            loss = criterion_tr(input=y_hat, target=y, parameters=model_parameters, surrogate_model=surrogate_model)

            loss_with_test_data.append(loss.item())

        y_test_predicted = torch.cat(y_test_predicted)

        colormap_train_predicted = ['b' if y > 0.5 else 'r' for y in y_train_predicted]
        colormap_test_predicted = ['b' if y > 0.5 else 'r' for y in y_test_predicted]

        X_train = X_train.to('cpu').detach().numpy()
        y_train = y_train.to('cpu').detach().numpy()
        X_test = X_test.to('cpu').detach().numpy()
        y_test = y_test.to('cpu').detach().numpy()

        fig, (ax1, ax2) = plt.subplots(2, 1)
        ax1.scatter(*X_train.T, c=colormap(y_train))
        ax1.set_title('Training data: ground truth')
        ax1.set_xlim([0, space[0]])
        ax1.set_ylim([0, space[1]])
        ax2.scatter(*X_train.T, c=colormap_train_predicted)
        ax2.set_xlim([0, space[0]])
        ax2.set_ylim([0, space[1]])
        ax2.set_title('Training data prediction')

        ax1.plot(x_decision_fun, y_decision_fun, 'k-')
        ax2.plot(x_decision_fun, y_decision_fun, 'k-')

        fig.tight_layout()

        writer.add_figure(f'Inference/Inference with training data, loss: {np.array(loss_with_train_data).mean()}', figure=fig)

        fig, (ax1, ax2) = plt.subplots(2, 1)
        ax1.scatter(*X_test.T, c=colormap(y_test))
        ax1.set_title('Test data: ground truth')
        ax1.set_xlim([0, space[0]])
        ax1.set_ylim([0, space[1]])
        ax2.scatter(*X_test.T, c=colormap_test_predicted)
        ax2.set_xlim([0, space[0]])
        ax2.set_ylim([0, space[1]])
        ax2.set_title('Test data prediction')

        ax1.plot(x_decision_fun, y_decision_fun, 'k-')
        ax2.plot(x_decision_fun, y_decision_fun, 'k-')

        fig.tight_layout()

        writer.add_figure(f'Inference/Inference with test data, loss: {np.array(loss_with_test_data).mean()}', figure=fig)

    y_pred = [1 if y > 0.5 else -1 for y in y_train_predicted]
    tn, fp, fn, tp = confusion_matrix(y_train, y_pred).ravel()
    acc_NN_train = accuracy_score(y_train, y_pred)
    data_summary = f'NN with train data  \n  \nTP: {tp}  \nFP: {fp}  \nFN: {fn}  \nTN: {tn}'
    writer.add_text('Confusion Matrices/NN with Train data', data_summary)
    writer.add_text('Accuracy/Accuracy of NN with Train data', f'Accuracy of NN with train data: {acc_NN_train:.4f}')

    y_pred = [1 if y > 0.5 else -1 for y in y_test_predicted]
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred).ravel()
    acc_NN_test = accuracy_score(y_test, y_pred)
    data_summary = f'NN with test data  \n  \nTP: {tp}  \nFP: {fp}  \nFN: {fn}  \nTN: {tn}'
    writer.add_text('Confusion Matrices/NN with Test data', data_summary)
    writer.add_text('Accuracy/Accuracy of NN with Test data', f'Accuracy of NN with test data: {acc_NN_test:.4f}')

    # Decision tree directly on input space
    final_decision_tree = DecisionTreeClassifier(random_state=42, min_samples_leaf=25)
    final_decision_tree.fit(X_train, y_train)
    #final_decision_tree = dtu.post_pruning(X_train, y_train, X_test, y_test, final_decision_tree)

    y_hat_with_tree = final_decision_tree.predict(X_test)
    acc_DT = accuracy_score(y_test, y_hat_with_tree)

    tn, fp, fn, tp = confusion_matrix(y_test, y_hat_with_tree).ravel()
    data_summary = f'DT before reg with test data  \n  \nTP: {tp}  \nFP: {fp}  \nFN: {fn}  \nTN: {tn}'
    writer.add_text('Confusion Matrices/DT with Test data', data_summary)
    writer.add_text('Accuracy/Accuracy of DT', f'Accuracy with DT before reg: {acc_DT:.4f}')

    #Export graph
    dot_data = StringIO()
    export_graphviz(final_decision_tree, out_file=dot_data, filled=True, rounded=True, special_characters=True,
                    feature_names=['x', 'y'],
                    class_names=['-1', '1'])
    graph = pydotplus.graph_from_dot_data(dot_data.getvalue())
    graph.write_png('figures/decision_tree.png')
    Image(graph.create_png())
    img = ImagePIL.open('figures/decision_tree.png')
    fig = plt.figure()
    plt.imshow(img)
    writer.add_figure(f'Decision Trees/DT before regularisation, Accuracy: {acc_DT:.4f}', fig)

    # Decision tree after regularization
    final_decision_tree = DecisionTreeClassifier(random_state=42, min_samples_split=25)
    y_train_predicted = [1 if y > 0.5 else -1 for y in y_train_predicted]
    final_decision_tree.fit(X_train, y_train_predicted)
    #final_decision_tree = dtu.post_pruning(X_train, y_train_predicted, X_test, y_test, final_decision_tree)

    y_hat_with_tree = final_decision_tree.predict(X_test)

    tn, fp, fn, tp = confusion_matrix(y_test, y_hat_with_tree).ravel()
    acc_DT_reg = accuracy_score(y_test, y_hat_with_tree)
    data_summary = f'DT after reg with test data  \n  \nTP: {tp}  \nFP: {fp}  \nFN: {fn}  \nTN: {tn}'
    writer.add_text('Confusion Matrices/DT reg with Test data', data_summary)
    writer.add_text('Accuracy/Accuracy of DT reg', f'Accuracy with DT after reg: {acc_DT_reg:.4f}')

    # Export graph
    dot_data = StringIO()
    export_graphviz(final_decision_tree, out_file=dot_data, filled=True, rounded=True, special_characters=True,
                    feature_names=['x', 'y'],
                    class_names=['-1', '1'])
    graph = pydotplus.graph_from_dot_data(dot_data.getvalue())
    graph.write_png('figures/decision_tree_reg.png')
    Image(graph.create_png())
    img = ImagePIL.open('figures/decision_tree_reg.png')
    fig = plt.figure()
    plt.imshow(img)
    writer.add_figure(f'Decision Trees/DT after regularisation, Accuracy: {acc_DT_reg:.4f}', fig)

    print(f'Accuracy of NN with training data: {acc_NN_train:.4f}')
    print(f'Accuracy of NN with test data: {acc_NN_test:.4f}')
    print(f'Accuracy of NN DT before regularisation with test data: {acc_DT:.4f}')
    print(f'Accuracy of NN DT after regularisation with test data: {acc_DT_reg:.4f}')

    writer.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--ep',
                        type=int,
                        required=False,
                        default=250,
                        help='Number of epochs')

    parser.add_argument('--batch',
                        type=int,
                        default=100,
                        required=False,
                        help='Batch size, default 100')

    parser.add_argument('--rs',
                        type=float,
                        required=False,
                        default=10e-4,
                        help='Regularization strength for the objective, default 10e-4')

    parser.add_argument('--epsilon',
                        type=float,
                        default=0.2,
                        required=False,
                        help='Deprecated: Regularization strength for the surrogate training, default 20e-2')

    parser.add_argument('--lr',
                        type=float,
                        required=False,
                        default=10e-4,
                        help='Learning rate, default 10e-4')

    parser.add_argument('--lr_sr',
                        type=float,
                        required=False,
                        default=10e-3,
                        help='Learning rate, default 10e-3')

    parser.add_argument('--rt',
                        type=bool,
                        required=False,
                        default=True,
                        help='Retrain network, default True')

    parser.add_argument('--sw',
                        type=bool,
                        required=False,
                        default=True,
                        help='Surrogate training with saved weights, default True')

    parser.add_argument('--sb',
                        type=int,
                        required=False,
                        default=25,
                        help='Input size for surrogate training, default 25')

    parser.add_argument('--s',
                        type=bool,
                        required=False,
                        default=False,
                        help='Sample new data')

    args = parser.parse_args()

    main()
