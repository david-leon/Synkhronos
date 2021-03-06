
import numpy as np
import theano
import theano.tensor as T
import theano.gpuarray
import lasagne.layers as L
from demos.resnet.common import build_resnet
from lasagne import updates
import pickle
import time
import multiprocessing as mp
import sys
sys.setrecursionlimit(50000)

N_CALLS = 20
PROFILE = False
BATCH = 32


def build_train_func(rank=0, **kwargs):
    print("rank: {} Building model".format(rank))
    resnet = build_resnet()

    print("Building training function")
    x = T.ftensor4('x')
    y = T.imatrix('y')

    prob = L.get_output(resnet['prob'], x, deterministic=False)
    loss = T.nnet.categorical_crossentropy(prob, y.flatten()).mean()
    params = L.get_all_params(resnet.values(), trainable=True)

    sgd_updates = updates.sgd(loss, params, learning_rate=1e-4)

    # make a function to compute and store the raw gradient
    f_train = theano.function(inputs=[x, y],
                              outputs=loss,  # (assumes this is an avg)
                              updates=sgd_updates)

    return f_train, "original"


def pickle_func(func):
    print("Pickling function")
    with open("test_pkl.pkl", "wb") as f:
        pickle.dump(func, f, pickle.HIGHEST_PROTOCOL)


def unpickle_func(rank=0, master_rank=0):
    if rank == master_rank:
        print("unpickling function (in master)")
    else:
        print("Unpickling function (in worker {})".format(rank))
    with open("test_pkl.pkl", "rb") as f:
        f_unpkl = pickle.load(f)
    # f_unpkl.trust_input = True  # (may avoid slowdown)
    return f_unpkl, "unpickled"


def test_one_process(gpu=0):
    theano.gpuarray.use("cuda" + str(gpu))

    f_train, train_name = build_train_func()
    pickle_func(f_train)
    f_unpkl, unpkl_name = unpickle_func()

    test_the_function(f_train, train_name)
    test_the_function(f_unpkl, unpkl_name)


def test_multi_process_sequence(n_gpu=2, worker_func_maker=unpickle_func):
    barrier = mp.Barrier(n_gpu)
    if PROFILE:
        target = seq_profiling_worker
    else:
        target = sequence_worker
    procs = [mp.Process(target=target,
                        args=(rank, n_gpu, barrier, worker_func_maker))
        for rank in range(1, n_gpu)]
    for p in procs:
        p.start()

    theano.gpuarray.use("cuda0")
    f_train, name = build_train_func()
    pickle_func(f_train)

    barrier.wait()
    # workers make function (maybe unpickle).
    barrier.wait()
    for i in range(n_gpu):
        time.sleep(1)
        barrier.wait()
        if i == 0:
            test_the_function(f_train, name)

    for p in procs:
        p.join()


def sequence_worker(rank, n_gpu, barrier, function_maker):
    theano.gpuarray.use("cuda" + str(rank))
    # maybe master makes the function
    barrier.wait()
    f_train, name = function_maker(rank=rank)  # maybe unpickle
    barrier.wait()
    for i in range(n_gpu):
        time.sleep(1)
        barrier.wait()
        if i == rank:
            test_the_function(f_train, name=name, rank=rank)


def test_multi_process_simultaneous(n_gpu=2, worker_func_maker=unpickle_func, bar_loop=False):
    barrier = mp.Barrier(n_gpu)
    if PROFILE:
        target = sim_profiling_worker
    else:
        target = simultaneous_worker
    procs = [mp.Process(target=target,
                        args=(rank, worker_func_maker, barrier, bar_loop))
            for rank in range(1, n_gpu)]
    for p in procs:
        p.start()

    theano.gpuarray.use("cuda0")
    f_train, name = build_train_func()

    barrier.wait()
    # workers build or unpickle
    time.sleep(1)
    barrier.wait()
    # workers are ready.
    test_the_function(f_train, name=name, barrier=barrier, bar_loop=bar_loop)

    for p in procs:
        p.join()


def simultaneous_worker(rank, function_maker, barrier, bar_loop):
    theano.gpuarray.use("cuda" + str(rank))
    # maybe master makes the function
    barrier.wait()
    f_train, name = function_maker(rank)
    barrier.wait()
    test_the_function(f_train, name=name, rank=rank, barrier=barrier, bar_loop=bar_loop)


def test_the_function(f, name="original", rank=0, barrier=None, bar_loop=False):
    print("Making synthetic data")
    data_len = BATCH * 10
    x_dat = np.random.randn(data_len, 3, 224, 224).astype("float32")
    y_dat = np.random.randint(low=0, high=1000, size=(data_len, 1)).astype("int32")

    # (Get different data each time)
    sample_idxs = [np.random.randint(low=0, high=data_len - 1, size=BATCH)
        for _ in range(N_CALLS)]

    print("rank: {} Running {} function".format(rank, name))
    r = 0
    for _ in range(10):
        r += f(x_dat[:BATCH], y_dat[:BATCH])
    if barrier is not None:
        barrier.wait()
    t_0 = time.time()
    for batch in sample_idxs:
        r += f(x_dat[batch], y_dat[batch])
        if bar_loop and barrier is not None:
            barrier.wait()
    t_1 = time.time()
    print("rank {}: {} function ran in {:,.3f} s  ({} calls)".format(
        rank, name, t_1 - t_0, N_CALLS))


def seq_profiling_worker(*args):
    import cProfile
    rank = args[0]
    cProfile.runctx('sequence_worker(*args)', locals(), globals(),
        "sequence_worker_{}.prof".format(rank))


def sim_profiling_worker(*args):
    import cProfile
    rank = args[0]
    cProfile.runctx('simultaneous_worker(*args)', locals(), globals(),
        "simultaneous_worker_{}.prof".format(rank))


if __name__ == "__main__":
    kwargs = {}
    if len(sys.argv) == 1 or sys.argv[1] in ["h", "-h", "help", "--help"]:
        help_text = """
        This script is for testing running speed of Theano functions before vs
        after pickling.  It uses an SGD training function on ResNet-50, taken
        from the demos/ folder.  A few different modes are possible, examples:

        python tests/function_pkl_test.py 1
        Uses only one GPU and tests the original + unpickled function on it

        python tests/function_pkl_test.py 1 2
        Same as above but uses "cuda2"

        python tests/function_pkl_test.py 2 seq unpkl
        Uses 2 GPUs
        Runs the functions in sequence (one worker at a time)
        workers use unpickled function

        python tests/function_pkl_test.py 3 seq orig
        Uses 3 GPUs
        Runs the functions in sequence
        workers build their own function (no unpickled functions)

        python tests/function_pkl_test.py 2 sim unpkl
        Uses 2 GPUs
        All GPUs start at same time (including master)
        workers use unpickled function

        python tests/function_pkl_test.py 8 sim orig c
        Uses 8 GPUs
        All GPUs start at same time
        workers build their own functions
        (any character) barrier.wait() called at every function call in loop

        Can use any combination of (seq, sim), (orig, pkl) (, c)

        Use PROFILE at the top of the file to turn on/off worker profiling

        (theano v0.9.0 may require function.trust_input = True in unpickled)

        """
    else:
        n_gpu = int(sys.argv[1])
        if n_gpu == 1:
            if len(sys.argv) > 2:
                kwargs["gpu"] = int(sys.argv[2])
            test_one_process(**kwargs)
        else:
            kwargs["n_gpu"] = n_gpu
            assert sys.argv[2] in ["seq", "sim"]  # sequence or simultaneous
            assert sys.argv[3] in ["orig", "unpkl"]  # workers make original or unpickle
            if sys.argv[3] == "orig":
                kwargs["worker_func_maker"] = build_train_func
            else:
                kwargs["worker_func_maker"] = unpickle_func
            if sys.argv[2] == "seq":
                test_multi_process_sequence(**kwargs)
            else:
                if len(sys.argv) > 4:
                    kwargs["bar_loop"] = True
                test_multi_process_simultaneous(**kwargs)
