.. synkhronos documentation master file, created by
   sphinx-quickstart on Tue Feb  7 17:51:00 2017.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.



==========
Synkhronos
==========
A Multi-GPU Theano Extension for Data Parallelism
-------------------------------------------------

Synkhronos is a Python package for accelerating computation of Theano functions under data parallelism with multiple GPUs.  The aim of this package is to speed up program execution with minimum changes to user code.  Variables and graphs are constructed as usual with Theano or extensions such as Lasagne.  Synkhronos replicates the user-constructed functions and GPU-memory variables on all devices.  The user calls these functions as in a serial program; parallel execution across all GPUs is automated.  Synkhronos supports management of Theano shared variables across devices, either by reading/writing individually or through collective communications, such as all-reduce, broadcast, etc.

Data parallelism requires that functions can equivalently be computed over an entire data set, or alternatively over subsets of the data with the multiple results reduced finally.  A common example in machine learning is the computation of a gradient as an expectation value over a minibatch of data (the minibatch can be sub-divided).


Function Batches and Slices
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Synkhronos further extends the Theano interface by supporting indexed and sliced function calls.  Variables contianing entire data sets can be passed to Synkhronos functions, with an optional input argument to tell which elements (selected by index in 0-th dimension) to use in the function call.  This can also be done for implicit inputs.

If the input data set is too large to compute on within the device memory, another optional input argument sets the number of "slices" each worker uses to compute over its assigned data.  Results are automatically accumulated over each input slice (each a separate call to the Theano function) within each worker before being reduced once back to the master.  This is convenient for running validation or test measurement functions in machine learning, for example.

Under the Hood
~~~~~~~~~~~~~~

When a Synkhronos function is called, it scatters the input data, executes the underlying Theano function simultaneously on all devices, and reduces the outputs back to the master process.  Functions may also update Theano shared memory variables (GPU-memory) locally on each device.  Collectives on Theano shared variables are provided through the NVIDIA Collective Communications Library (NCCL, via PyGPU), or through CPU-based mechanisms.

Using Multiprocessing, a separate python process is forked for each additional GPU.  Explicit function inputs are scattered via OS shared memory.  This facilitates greater speedup by minimizing and parallelizing memory copies.  Data may be scattered to GPU memories ahead of time for implicit function inputs; this is advantageous for data used repeatedly, device memory permitting.

Barriers guard the execution, both start and finish, of any function or method that requires worker action.  This provides a programming framework safe from race conditions and lends the package its name.

This package currently provides for single-node computing only.

Contents:
~~~~~~~~~

See the following pages for installation instructions, simple examples, and function reference.  See the folder ``Synkhronos/demos`` for more complete examples including MNIST and ResNet-50.  It is suggested to read the code and execute the demos to see printed results.

.. toctree::
   :maxdepth: 2
   :numbered:

   pages/installation.rst
   pages/intro_example.rst
   pages/theano_shared.rst
   pages/deep_learning.rst
   pages/api.rst


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

