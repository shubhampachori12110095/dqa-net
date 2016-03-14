import json
import os
import shutil
from pprint import pprint

import h5py
import tensorflow as tf

from configs.get_config import get_config
from configs.c04 import configs
from models.attention_model_04 import AttentionModel
from read_data.r04 import read_data

flags = tf.app.flags

# File directories
flags.DEFINE_string("log_dir", "log", "Log directory [log]")
flags.DEFINE_string("model_name", "model_03", "Model name [model_03]")
flags.DEFINE_string("data_dir", "data/s3", "Data directory [data/s3]")
flags.DEFINE_string("fold_path", "data/s3/fold6.json", "fold json path [data/s3/fold6.json]")

# Training parameters
flags.DEFINE_integer("batch_size", 100, "Batch size for the network [100]")
flags.DEFINE_integer("hidden_size", 100, "Hidden size [100]")
flags.DEFINE_integer("image_size", 4096, "Image size [4096]")
flags.DEFINE_integer("num_layers", 3, "Number of layers [3]")
flags.DEFINE_integer("rnn_num_layers", 1, "Number of rnn layers [2]")
flags.DEFINE_integer("emb_num_layers", 0, "Number of embedding layers [3]")
flags.DEFINE_float("init_mean", 0, "Initial weight mean [0]")
flags.DEFINE_float("init_std", 0.1, "Initial weight std [0.1]")
flags.DEFINE_float("init_lr", 0.01, "Initial learning rate [0.01]")
flags.DEFINE_float("init_nw", 0.9, "Initial null weight [0.9]")
flags.DEFINE_integer("anneal_period", 20, "Anneal period [20]")
flags.DEFINE_float("anneal_ratio", 0.5, "Anneal ratio [0.5")
flags.DEFINE_integer("num_epochs", 50, "Total number of epochs for training [50]")
flags.DEFINE_boolean("linear_start", False, "Start training with linear model? [False]")
flags.DEFINE_float("max_grad_norm", 40, "Max grad norm; above this number is clipped [40]")
flags.DEFINE_float("keep_prob", 1.0, "Keep probability of dropout [0.5]")
flags.DEFINE_string("sim_func", 'man_dist', "Similarity function: man_dist | dot [man_dist]")
flags.DEFINE_string("max_func", 'max', "Max function: max | var | combined [max]")
flags.DEFINE_string("lstm", "regular", "LSTM cell type: regular | basic | GRU [regular]")
flags.DEFINE_float("forget_bias", 2.5, "LSTM forget bias for basic cell [0.0]")
flags.DEFINE_float("cell_clip", 40, "LSTM cell clipping for regular cell [40]")
flags.DEFINE_string("opt", 'basic', 'Optimizer: basic | adagrad [basic]')
flags.DEFINE_float("rand_y", 1.0, "Rand y. [1.0]")
flags.DEFINE_boolean("use_null", False, "Use null weight [False]")

# Training and testing options
flags.DEFINE_boolean("train", False, "Train? Test if False [False]")
flags.DEFINE_integer("val_num_batches", 5, "Val num batches [5]")
flags.DEFINE_boolean("load", False, "Load from saved model? [False]")
flags.DEFINE_boolean("progress", True, "Show progress? [True]")
flags.DEFINE_boolean("gpu", False, 'Enable GPU? (Linux only) [False]')
flags.DEFINE_integer("val_period", 5, "Val period (for display purpose only) [5]")
flags.DEFINE_integer("save_period", 10, "Save period [10]")
flags.DEFINE_integer("config", -1, "Config number to load. -1 to use currently defined config. [-1]")
flags.DEFINE_string("mode", "la", "l | la [la]")
flags.DEFINE_boolean("dot_diff_sim", False, "use DotDiffSim? [False]")
flags.DEFINE_string("model", "sim", "sim | att [sim]")

# Debugging
flags.DEFINE_boolean("draft", False, "Draft? (quick build) [False]")

# App-specific training parameters
# TODO : Any other parameters

# App-specific options
# TODO : Any other options

FLAGS = flags.FLAGS

def mkdirs(config):
    eval_dir = "evals/%s" % config.model_name
    eval_subdir = os.path.join(eval_dir, "c%s" % str(config.config).zfill(2))
    log_dir = "logs/%s" % config.model_name
    log_subdir = os.path.join(log_dir, "c%s" % str(config.config).zfill(2))
    save_dir = "saves/%s" % config.model_name
    save_subdir = os.path.join(save_dir, "c%s" % str(config.config).zfill(2))
    config.eval_dir = eval_subdir
    config.log_dir = log_subdir
    config.save_dir = save_subdir

    if not os.path.exists(eval_dir):
        os.mkdir(eval_dir)
    if os.path.exists(eval_subdir):
        if config.train and not config.load:
            shutil.rmtree(eval_subdir)
            os.mkdir(eval_subdir)
    else:
        os.mkdir(eval_subdir)
    if not os.path.exists(log_dir):
        os.mkdir(log_dir)
    if os.path.exists(log_subdir):
        if config.train and not config.load:
            shutil.rmtree(log_subdir)
            os.mkdir(log_subdir)
    else:
        os.mkdir(log_subdir)
    if config.train:
        if not os.path.exists(save_dir):
            os.mkdir(save_dir)
        if os.path.exists(save_subdir):
            if not config.load:
                shutil.rmtree(save_subdir)
                os.mkdir(save_subdir)
        else:
            os.mkdir(save_subdir)


def load_meta_data(config):
    meta_data_path = os.path.join(config.data_dir, "meta_data.json")
    meta_data = json.load(open(meta_data_path, "r"))

    # Other parameters
    config.max_sent_size = meta_data['max_sent_size']
    config.max_fact_size = meta_data['max_fact_size']
    config.max_num_facts = meta_data['max_num_facts']
    config.num_choices = meta_data['num_choices']
    config.vocab_size = meta_data['vocab_size']
    config.word_size = meta_data['word_size']


def main(_):
    config_dict = configs[FLAGS.config] if FLAGS.config >= 0 else {}
    config = get_config(FLAGS.__flags, config_dict, 1)
    config.main_name = __name__

    load_meta_data(config)
    mkdirs(config)

    # load other files
    init_emb_mat_path = os.path.join(config.data_dir, 'init_emb_mat.h5')
    config.init_emb_mat = h5py.File(init_emb_mat_path, 'r')['data'][:]

    if config.train:
        train_ds = read_data(config, 'train')
        val_ds = read_data(config, 'val')
        config.train_num_batches = train_ds.num_batches
        config.val_num_batches = min(config.val_num_batches, train_ds.num_batches, val_ds.num_batches)


    else:
        test_ds = read_data(config, 'test')
        config.test_num_batches = test_ds.num_batches

    # For quick draft build (deubgging).
    if config.draft:
        config.train_num_batches = 1
        config.val_num_batches = 1
        config.test_num_batches = 1
        config.num_epochs = 1
        config.val_period = 1
        config.save_period = 1
        # TODO : Add any other parameter that induces a lot of computations
        config.num_layers = 1
        config.rnn_num_layers = 1

    pprint(config.__dict__)

    graph = tf.Graph()
    model = AttentionModel(graph, config)
    eval_tensors = [model.yp, model.sim.p]
    with tf.Session(graph=graph) as sess:
        sess.run(tf.initialize_all_variables())
        if config.train:
            writer = tf.train.SummaryWriter(config.log_dir, sess.graph_def)
            if config.load:
                model.load(sess)
            model.train(sess, writer, train_ds, val_ds, eval_tensors=eval_tensors)
        else:
            model.load(sess)
            model.eval(sess, test_ds, eval_tensors=eval_tensors)

if __name__ == "__main__":
    tf.app.run()
