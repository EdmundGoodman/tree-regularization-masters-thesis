import copy
import torch
from dtreeviz.trees import *
from sklearn.tree import DecisionTreeClassifier
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import cross_val_score
from sklearn.metrics import accuracy_score
from sklearn.tree import export_graphviz
from six import StringIO
from IPython.display import Image
from PIL import Image as ImagePIL
import pydotplus

np.random.seed(5555)
device = "mps" if torch.backends.mps.is_available() else 'cpu'


def get_data_loader(X_train, y_train, X_test, y_test, X_val, y_val, X_type, y_type, batch_size):
    """Get data loader given training, validation and test data.

        Parameters
        ----------
        X_train: Training data features

        y_train: Labels for training data

        X_test: Test data features

        y_test: Labels for test data

        X_val: Validation data features

        y_val: Labels for validation data

        X_type: Data type for input features

        y_type: Data type for labels

        batch_size: Batch size for mini-batches

        Returns
        -------
        data_train_loader : Data loader for training data

        data_test_loader : Data loader for test data

        data_val_loader : Data loader for validation data
    """

    X_train = torch.tensor(X_train, dtype=X_type).to(device)
    X_test = torch.tensor(X_test, dtype=X_type).to(device)
    X_val = torch.tensor(X_val, dtype=X_type).to(device)

    if len(y_train.shape) <= 2:
        y_train = torch.tensor(y_train.reshape(-1, 1), dtype=y_type).to(device)
        y_test = torch.tensor(y_test.reshape(-1, 1), dtype=y_type).to(device)
        y_val = torch.tensor(y_val.reshape(-1, 1), dtype=y_type).to(device)
    else:
        y_train = torch.tensor(y_train, dtype=y_type).to(device)
        y_test = torch.tensor(y_test, dtype=y_type).to(device)
        y_val = torch.tensor(y_val, dtype=y_type).to(device)

    data_train = TensorDataset(X_train, y_train)
    data_train_loader = DataLoader(dataset=data_train, batch_size=batch_size, shuffle=True)
    data_test = TensorDataset(X_test, y_test)
    data_test_loader = DataLoader(dataset=data_test, batch_size=batch_size)
    data_val = TensorDataset(X_val, y_val)
    data_val_loader = DataLoader(dataset=data_val, batch_size=batch_size)

    return data_train_loader, data_test_loader, data_val_loader


def dataloader_to_numpy(dataloader):
    """Convert data loader to numpy arrays.

        Parameters
        ----------
        dataloader: torch data loader


        Returns
        -------
        X : Features as numpy array

        y: Labels as numpy array
    """

    X = dataloader.dataset[:][0].detach().cpu().numpy()
    y = dataloader.dataset[:][1].detach().cpu().numpy()

    return X, y


def colormap(Y):
    """Convert labels Y into a color-coding list. If y = 0, the color is 'r' (red), otherwise 'b' (blue)

        Parameters
        ----------
        Y: Labels

        Returns
        -------
        colormap: color-coding for Y
    """
    colormap = ['b' if y == 1 else 'r' for y in Y]

    return colormap


def post_pruning(X, y):
    """Minimal-complexity post-pruning for large decision trees. Given data set (X,y), train a decision tree classifier
    and compute the ccp_alphas from possible pruning paths. Do cross-validation with 5 folds and use one-standard-error
    rule to get the most parsimonous tree.

        Parameters
        ----------
        X: Input features

        y: Labels

        Returns
        -------
        ccp_alpha: Selected best alpha a*
    """
    # https://medium.com/swlh/post-pruning-decision-trees-using-python-b5d4bcda8e23
    # https://scikit-learn.org/stable/auto_examples/tree/plot_cost_complexity_pruning.html#sphx-glr-auto-examples-tree-plot-cost-complexity-pruning-py

    clf = DecisionTreeClassifier(random_state=42)
    path = clf.cost_complexity_pruning_path(X, y)
    ccp_alphas, impurities = path.ccp_alphas, path.impurities
    ccp_alphas = ccp_alphas[:-1]
    scores = []
    if len(ccp_alphas) != 0:
        for ccp_alpha in ccp_alphas:
            clf = DecisionTreeClassifier(ccp_alpha=ccp_alpha)
            score = cross_val_score(clf, X, y, cv=5, scoring="neg_mean_squared_error", n_jobs=-1)
            scores.append(score)

        # average over folds, fix sign of mse
        fold_mse = -np.mean(scores, 1)
        # select the most parsimonous model (highest ccp_alpha) that has an error within one standard deviation of
        # the minimum mse.
        # I.e. the "one-standard-error" rule (see ESL or a lot of other tibshirani / hastie notes on regularization)
        selected_alpha = np.max(ccp_alphas[fold_mse <= np.min(fold_mse) + np.std(fold_mse)])

        return selected_alpha

    else:
        return 0.0

def build_decision_tree(X_train, y_train, X_test, y_test, space, path, epoch=0, contour_plot=True, min_samples_leaf=1):
    """Build tree given input data and save the corresponding tree plot and contour plot.

        Parameters
        ----------
        X_train: Training data features

        y_train: Labels for training data

        X_test: Test data features

        y_test: Labels for test data

        space: Feature space

        path: Directory, where the plots should be stored

        epoch: Current training epoch, where the snapshot takes place

        contour_plot: Default True, if the contour plots should be drawn (only for 2-dimensional feature space)

        min_samples_leaf: Pre-pruning method, default 1 (no pruning)

        Returns
        -------
        accuracy: Accuracy measure of the decision tree using training and test set
    """

    ccp_alpha = post_pruning(X_train, y_train)
    clf = DecisionTreeClassifier(random_state=42, ccp_alpha=ccp_alpha)
    clf.fit(X_train, y_train)

    y_hat_tree = clf.predict(X_test)
    accuracy = accuracy_score(y_test, y_hat_tree)

    dot_data = StringIO()
    export_graphviz(
        decision_tree=clf,
        out_file=dot_data,
        filled=True,
        rounded=True,
        special_characters=True,
        feature_names=['x', 'y'],
        class_names=['0', '1'])
    graph = pydotplus.graph_from_dot_data(dot_data.getvalue())
    graph.write_png(f'{path}.png')
    Image(graph.create_png())

    if contour_plot:
        xx, yy = np.meshgrid(np.linspace(space[0][0], space[0][1], 100),
                             np.linspace(space[0][0], space[0][1], 100))
        # plt.tight_layout(h_pad=0.5, w_pad=0.5, pad=2.5)

        Z = clf.predict(np.c_[xx.ravel(), yy.ravel()]).reshape(xx.shape)
        fig_contour = plt.figure()
        plt.contourf(xx, yy, Z, cmap=plt.cm.RdYlBu)
        # plt.scatter(*X_test.T, c=colormap(y_test), edgecolors='k')
        plt.title(f'Tree Parabola Contourplot Epoch {epoch}')
        # plt.tight_layout()
        plt.savefig(f'{path}_contourplot.png')
        plt.close(fig_contour)

    return accuracy

def pred_contours(x, y, model):
    """Given input data, compute the contours of the prediciont to draw the contour plots.

        Parameters
        ----------
        x: Input data as meshgrid

        y: Labels as meshgrid

        model: Trained deep model


        Returns
        -------
        y_pred : Model predictions as predictions contours
    """

    data = np.c_[x.ravel(), y.ravel()]
    y_pred = []

    for d in data:
        y_hat = model(torch.tensor(d, dtype=torch.float, device='mps'))
        y_pred.append(y_hat.detach().cpu().numpy())

    y_pred = np.array(y_pred)
    y_pred = np.where(y_pred > 0.5, 1, 0)

    return y_pred


def augment_data_with_dirichlet(X_train, parameters, model, device, num_new_samples):
    """Draw new synthetic data for surrogate model using Dirichlet distribution.

        Parameters
        ----------
        X_train: Training data features

        parameters: Set of model parameters

        model: Target deep model

        device: Device, where the model is been trained (cpu or gpu)

        num_new_samples: Desired of new synthetic samples

        Returns
        -------
        parameters_new: New synthetic parameter set

        APLs_new: New synthetic APL estiamtes
    """

    parameters_new = []
    APLs_new = []

    alpha = [1] * len(parameters)
    samples = np.random.dirichlet(alpha, num_new_samples)
    parameters = torch.vstack(parameters).to(device)
    samples = torch.from_numpy(samples).float().to(device)
    parameters_ = samples @ parameters

    model.to(device)
    model.eval()

    for param in parameters_:
        model.vector_to_parameters(param)
        APL = model.compute_APL(X_train)

        parameters_new.append(param)
        APLs_new.append(APL)

    del model
    del parameters_
    del samples

    return parameters_new, APLs_new


def augment_data_with_gaussian(X_train, model, device, size):
    """ DEPRECATED
    Draw new synthetic data for surrogate model using Gaussian distribution.

        Parameters
        ----------
        X_train: Training data features

        parameters: Set of model parameters

        model: Target deep model

        device: Device, where the model is been trained (cpu or gpu)

        num_new_samples: Desired of new synthetic samples

        Returns
        -------
        parameters_new: New synthetic parameter set

        APLs_new: New synthetic APL estiamtes
    """

    parameters = []
    APLs = []

    for _ in range(size):

        model_copy = copy.deepcopy(model)
        model_copy.eval()

        for param in model_copy.feed_forward.parameters():
            param.data.requires_grad = False

            # variance: 0.1 - 0.3 times relative to the absolute value of the model parameter
            param_augmented = np.random.normal(param.data.cpu().numpy(), 0.1 * np.abs(param.data.cpu().numpy()))
            param.data = torch.tensor(param_augmented, dtype=torch.float).float().to(device)

        parameters.append(model_copy.get_parameter_vector)
        APLs.append(model_copy.compute_APL(X_train))

        del model_copy

    return parameters, APLs
