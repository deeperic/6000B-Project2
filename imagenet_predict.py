# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Runs a ResNet model on the ImageNet dataset."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import os
import sys

import tensorflow as tf

import resnet_model
import vgg_preprocessing

parser = argparse.ArgumentParser()

parser.add_argument(
    '--data_dir', type=str, default='',
    help='The directory where the ImageNet input data is stored.')

parser.add_argument(
    '--model_dir', type=str, default='/tmp/resnet_model',
    help='The directory where the model will be stored.')

parser.add_argument(
    '--resnet_size', type=int, default=50, choices=[18, 34, 50, 101, 152, 200],
    help='The size of the ResNet model to use.')

parser.add_argument(
    '--train_epochs', type=int, default=100,
    help='The number of epochs to use for training.')

parser.add_argument(
    '--epochs_per_eval', type=int, default=1,
    help='The number of training epochs to run between evaluations.')

parser.add_argument(
    '--batch_size', type=int, default=32,
    help='Batch size for training and evaluation.')

parser.add_argument(
    '--data_format', type=str, default=None,
    choices=['channels_first', 'channels_last'],
    help='A flag to override the data format used in the model. channels_first '
         'provides a performance boost on GPU but is not always compatible '
         'with CPU. If left unspecified, the data format will be chosen '
         'automatically based on whether TensorFlow was built for CPU or GPU.')

#_DEFAULT_IMAGE_SIZE = 224
_DEFAULT_IMAGE_SIZE = 196
_NUM_CHANNELS = 3
_LABEL_CLASSES = 6

_MOMENTUM = 0.9
_WEIGHT_DECAY = 1e-4

'''
_NUM_IMAGES = {
    'train': 1281167,
    'validation': 50000,
}
'''
_NUM_IMAGES = {
    'train': 2569,
    'validation': 550,
}

#_FILE_SHUFFLE_BUFFER = 1024
#_SHUFFLE_BUFFER = 1500


_FILE_SHUFFLE_BUFFER = 500
_SHUFFLE_BUFFER = 500


def filenames111(is_training, data_dir):
  """Return filenames for dataset."""
  if is_training:
    return [
        os.path.join(data_dir, 'train-%05d-of-00004' % i)
        for i in range(4)]
  else:
    return [
        os.path.join(data_dir, 'validation-%05d-of-00004' % i)
        for i in range(4)]


def filenames(is_training, data_dir):
  """Return filenames for dataset."""
  if is_training:
    return [
        os.path.join(data_dir, 'train-%05d-of-00001' % i)
        for i in range(1)]
  else:
    return [
        os.path.join(data_dir, 'validation-%05d-of-00001' % i)
        for i in range(1)]

def filenames_test(data_dir):
  """Return filenames for dataset."""
  return [
      os.path.join(data_dir, 'test-%05d-of-00001' % i)
      for i in range(1)]

		
def record_parser(value, is_training):
  """Parse an ImageNet record from `value`."""
  keys_to_features = {
      'image/encoded':
          tf.FixedLenFeature((), tf.string, default_value=''),
      'image/format':
          tf.FixedLenFeature((), tf.string, default_value='jpeg'),
	  'image/filename':
          tf.FixedLenFeature((), tf.string, default_value='dummy filename'),
      'image/class/label':
          tf.FixedLenFeature([], dtype=tf.int64, default_value=-1),
      'image/class/text':
          tf.FixedLenFeature([], dtype=tf.string, default_value=''),
      'image/object/bbox/xmin':
          tf.VarLenFeature(dtype=tf.float32),
      'image/object/bbox/ymin':
          tf.VarLenFeature(dtype=tf.float32),
      'image/object/bbox/xmax':
          tf.VarLenFeature(dtype=tf.float32),
      'image/object/bbox/ymax':
          tf.VarLenFeature(dtype=tf.float32),
      'image/object/class/label':
          tf.VarLenFeature(dtype=tf.int64),
  }

  parsed = tf.parse_single_example(value, keys_to_features)

  image = tf.image.decode_image(
      tf.reshape(parsed['image/encoded'], shape=[]),
      _NUM_CHANNELS)
  image = tf.image.convert_image_dtype(image, dtype=tf.float32)

  image = vgg_preprocessing.preprocess_image(
      image=image,
      output_height=_DEFAULT_IMAGE_SIZE,
      output_width=_DEFAULT_IMAGE_SIZE,
      is_training=is_training)

  label = tf.cast(
      tf.reshape(parsed['image/class/label'], shape=[]),
      dtype=tf.int32)

  return image, tf.one_hot(label, _LABEL_CLASSES)


def input_fn(is_test, is_training, data_dir, batch_size, num_epochs=1):
  """Input function which provides batches for train or eval."""
  dataset = tf.data.Dataset.from_tensor_slices(filenames(is_training, data_dir))
  
  if(is_test == True):
    dataset = tf.data.Dataset.from_tensor_slices(filenames_test(data_dir))
  
  print(dataset.output_shapes)

  if is_training:
    dataset = dataset.shuffle(buffer_size=_FILE_SHUFFLE_BUFFER)

  dataset = dataset.flat_map(tf.data.TFRecordDataset)
  dataset = dataset.map(lambda value: record_parser(value, is_training),
                        num_parallel_calls=5)
  dataset = dataset.prefetch(batch_size)

  if is_training:
    # When choosing shuffle buffer sizes, larger sizes result in better
    # randomness, while smaller sizes have better performance.
    dataset = dataset.shuffle(buffer_size=_SHUFFLE_BUFFER)

  # We call repeat after shuffling, rather than before, to prevent separate
  # epochs from blending together.
  dataset = dataset.repeat(num_epochs)
  dataset = dataset.batch(batch_size)

  iterator = dataset.make_one_shot_iterator()
  images, labels = iterator.get_next()
  return images, labels


def resnet_model_fn(features, labels, mode, params):
  """Our model_fn for ResNet to be used with our Estimator."""
  tf.summary.image('images', features, max_outputs=6)

  network = resnet_model.imagenet_resnet_v2(
      params['resnet_size'], _LABEL_CLASSES, params['data_format'])
  logits = network(
      inputs=features, is_training=(mode == tf.estimator.ModeKeys.TRAIN))

  predictions = {
      'classes': tf.argmax(logits, axis=1),
      'probabilities': tf.nn.softmax(logits, name='softmax_tensor')
  }

  if mode == tf.estimator.ModeKeys.PREDICT:
    return tf.estimator.EstimatorSpec(mode=mode, predictions=predictions)

  # Calculate loss, which includes softmax cross entropy and L2 regularization.
  cross_entropy = tf.losses.softmax_cross_entropy(
      logits=logits, onehot_labels=labels)

  # Create a tensor named cross_entropy for logging purposes.
  tf.identity(cross_entropy, name='cross_entropy')
  tf.summary.scalar('cross_entropy', cross_entropy)

  # Add weight decay to the loss. We perform weight decay on all trainable
  # variables, which includes batch norm beta and gamma variables.
  loss = cross_entropy + _WEIGHT_DECAY * tf.add_n(
      [tf.nn.l2_loss(v) for v in tf.trainable_variables()])

  if mode == tf.estimator.ModeKeys.TRAIN:
    # Scale the learning rate linearly with the batch size. When the batch size
    # is 256, the learning rate should be 0.1.
    initial_learning_rate = 0.1 * params['batch_size'] / 256
    batches_per_epoch = _NUM_IMAGES['train'] / params['batch_size']
    global_step = tf.train.get_or_create_global_step()

    # Multiply the learning rate by 0.1 at 30, 60, 80, and 90 epochs.
    boundaries = [
        int(batches_per_epoch * epoch) for epoch in [30, 60, 80, 90]]
    values = [
        initial_learning_rate * decay for decay in [1, 0.1, 0.01, 1e-3, 1e-4]]
    learning_rate = tf.train.piecewise_constant(
        tf.cast(global_step, tf.int32), boundaries, values)

    # Create a tensor named learning_rate for logging purposes.
    tf.identity(learning_rate, name='learning_rate')
    tf.summary.scalar('learning_rate', learning_rate)

    optimizer = tf.train.MomentumOptimizer(
        learning_rate=learning_rate,
        momentum=_MOMENTUM)

    # Batch norm requires update_ops to be added as a train_op dependency.
    update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
    with tf.control_dependencies(update_ops):
      train_op = optimizer.minimize(loss, global_step)
  else:
    train_op = None

  accuracy = tf.metrics.accuracy(
      tf.argmax(labels, axis=1), predictions['classes'])
  metrics = {'accuracy': accuracy}

  # Create a tensor named train_accuracy for logging purposes.
  tf.identity(accuracy[1], name='train_accuracy')
  tf.summary.scalar('train_accuracy', accuracy[1])

  return tf.estimator.EstimatorSpec(
      mode=mode,
      predictions=predictions,
      loss=loss,
      train_op=train_op,
      eval_metric_ops=metrics)


def main(unused_argv):
  # Using the Winograd non-fused algorithms provides a small performance boost.
  os.environ['TF_ENABLE_WINOGRAD_NONFUSED'] = '1'

  # Set up a RunConfig to only save checkpoints once per training cycle.
  run_config = tf.estimator.RunConfig().replace(save_checkpoints_secs=1e9)
  resnet_classifier = tf.estimator.Estimator(
      model_fn=resnet_model_fn, model_dir=FLAGS.model_dir, config=run_config,
      params={
          'resnet_size': FLAGS.resnet_size,
          'data_format': FLAGS.data_format,
          'batch_size': FLAGS.batch_size,
      })
  
  print('train_ecochs:' + str(FLAGS.train_epochs))
  print('epochs_per_eval:' + str(FLAGS.epochs_per_eval))
  
  for x in range(FLAGS.train_epochs // FLAGS.epochs_per_eval):
    print('x:' + str(x))
    tensors_to_log = {
        'learning_rate': 'learning_rate',
        'cross_entropy': 'cross_entropy',
        'train_accuracy': 'train_accuracy'
    }

    logging_hook = tf.train.LoggingTensorHook(
        tensors=tensors_to_log, every_n_iter=100)

    '''
    print('Starting a training cycle.')
    resnet_classifier.train(
        input_fn=lambda: input_fn(
            True, FLAGS.data_dir, FLAGS.batch_size, FLAGS.epochs_per_eval),
        hooks=[logging_hook])

    if(x > 9 and (x % 10 == 0)):
      print('Starting to evaluate.')
      eval_results = resnet_classifier.evaluate(
          input_fn=lambda: input_fn(False, FLAGS.data_dir, FLAGS.batch_size))
      print(eval_results)
    '''
	
    print('Starting to evaluate.')
    eval_results = resnet_classifier.evaluate(
          input_fn=lambda: input_fn(False, False, FLAGS.data_dir, FLAGS.batch_size))
    print(eval_results)
	  
    print('Starting to predict the evaluations for checking.')
    predictions = resnet_classifier.predict(
          input_fn=lambda: input_fn(False, False, FLAGS.data_dir, FLAGS.batch_size))
    #print(predictions)
    for i, p in enumerate(predictions):
        label = int(p["classes"]) - 0
        print("Evaluation labels %s: %s" % (i + 1, label) )
    #predicted_classes = [p['classes'] for p in predictions]
    #print('class predictions:' + str(predicted_classes))
	
    print('Starting to predict the test data.')
    predictions = resnet_classifier.predict(
          input_fn=lambda: input_fn(True, False, FLAGS.data_dir, FLAGS.batch_size))
    #print(predictions)
    output_label = []
    for i, p in enumerate(predictions):
        label = int(p["classes"]) - 1
        print("Test Data Prediction %s: %s" % (i + 1, label) )
        output_label.append(label)
		
    # Open a file
    fo = open("d:\\proj\\deeplearning\\project2\\predictions.txt", "w+")

    # Write sequence of lines at the end of the file.
    for item in output_label:
        fo.write("%d\n" % item)

    # Close opend file
    fo.close()
	
    break #exit the loop
	
	
if __name__ == '__main__':

  config = tf.ConfigProto(allow_soft_placement=True)
  config.gpu_options.allocator_type = 'BFC'
  #config.gpu_options.per_process_gpu_memory_fraction = 0.40
  config.gpu_options.allow_growth=True

  tf.logging.set_verbosity(tf.logging.INFO)
  FLAGS, unparsed = parser.parse_known_args()
  tf.app.run(argv=[sys.argv[0]] + unparsed)
