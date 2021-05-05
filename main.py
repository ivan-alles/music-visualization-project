import cv2
from musicnn.extractor import extractor
import numpy as np
import os
import shutil
import subprocess
import tensorflow as tf

# AUDIO_FILE = r'songs\pop.00000.wav'
AUDIO_FILE = r'songs\metal.00000-s.wav'
# AUDIO_FILE = r'songs\classical.00012.wav'

MUSICNN_MODEL = 'MSD_musicnn'
# MUSICNN_MODEL = 'MSD_vgg'

MUSICNN_INPUT_LENGTH = 0.25

DEEP_DREAM_MODEL = 'inception5h/tensorflow_inception_graph.pb'

IMAGENET_MEAN = 117.0
LAYER_NAMES = ['mixed3a', 'mixed4a', 'mixed4e', 'mixed5b']
LAYER_WEIGHTS = [3, 4, 2, 1]
LEARNING_RATE = 2
START_IMAGE_SIZE = 8
MAX_IMAGE_SIZE = 300
OCTAVE_SCALE = 1.4
ITERATION_COUNT = 5
MIX_RNG_SEED = 1
FEATURE_THRESHOLD = 0.1

OUTPUT_DIR = 'output'



def make_keyframes():
    # Features with time axis: mean_pool, max_pool, penultimate
    taggram, tags, feature_map = extractor(AUDIO_FILE, model=MUSICNN_MODEL, input_length=MUSICNN_INPUT_LENGTH)
    print(f'Musicnn features: {feature_map.keys()}')

    song_features = feature_map['mean_pool']

    graph = tf.Graph()
    sess = tf.InteractiveSession(graph=graph)

    with tf.gfile.FastGFile(DEEP_DREAM_MODEL, "rb") as f:
        graph_def = tf.GraphDef()
        graph_def.ParseFromString(f.read())

    # define input
    X = tf.placeholder(tf.float32, name="input")
    X2 = tf.expand_dims(X - IMAGENET_MEAN, 0)
    tf.import_graph_def(graph_def, {"input": X2})

    losses = []
    targets = []
    layers = []
    num_features = 0
    for layer_name in LAYER_NAMES:
        layer = graph.get_tensor_by_name("import/%s:0" % layer_name)
        layers.append(layer)
        num_features += int(layer.shape[-1])
        print(f'Layer {layer_name}, shape {layer.shape}')
        target = tf.placeholder(tf.float32, name="target")
        targets.append(target)
        # loss = tf.reduce_mean(tf.sqrt(tf.square(layer - target)))
        loss = tf.reduce_mean(layer * target)
        losses.append(loss)

    loss = losses[0] * LAYER_WEIGHTS[0]
    for i in range(1, len(losses)):
        loss = loss + losses[i] * LAYER_WEIGHTS[i]

    gradient = tf.gradients(loss, X)[0]

    for fi in range(len(song_features)):
        image_size = START_IMAGE_SIZE
        image = np.full((image_size, image_size, 3), IMAGENET_MEAN, dtype=np.float32)

        target_values = []
        features = song_features[fi]
        scale = int(num_features / len(features) * 4)
        scale = scale if scale % 2 else scale + 1
        features = cv2.resize(np.tile(features, (scale, 1)), (num_features, scale),
                              interpolation=cv2.INTER_LINEAR)[scale // 2]
        features = (features > FEATURE_THRESHOLD).astype(np.float32)
        print(f'Non-zero features {features.sum() / len(features) * 100:0.1f}%')
        np.random.RandomState(MIX_RNG_SEED).shuffle(features)
        start = 0
        for l in range(len(layers)):
            layer = layers[l]
            target_size = int(layer.shape[3])
            t = features[start:start+target_size]
            start += target_size
            target_values.append(t)

        while image_size < MAX_IMAGE_SIZE:
            # l = sess.run(layer, {X: image})
            # print(f'size {image.shape} l shape {l.shape} l range {l.min()} {l.max()}')

            for batch in range(ITERATION_COUNT):
                args = {X: image}
                for t in range(len(targets)):
                    args[targets[t]] = target_values[t]
                g = sess.run(gradient, args)
                image += LEARNING_RATE * g / (np.abs(g).mean() + 1e-7)
                view_image = (image - image.min()) / (image.max() - image.min())
                view_image = np.power(view_image, 1.5)
                cv2.imshow(f'result-{image_size}', view_image)
                cv2.waitKey(1)
            image_size *= OCTAVE_SCALE
            image = cv2.resize(image, (int(image_size), int(image_size)), interpolation=cv2.INTER_CUBIC)

        cv2.imwrite(os.path.join(OUTPUT_DIR, f'img-{fi:05d}.png'), image)

def make_movie():
    subprocess.run(
        [
            'ffmpeg', '-y',
            '-pix_fmt', 'yuv420p',
            '-framerate', f'{1 / MUSICNN_INPUT_LENGTH}',
            '-start_number', '0',
            '-i', 'output\img-%05d.png',
            '-r', '25',
            '-i', AUDIO_FILE,
            os.path.join(OUTPUT_DIR, os.path.splitext(os.path.basename(AUDIO_FILE))[0] + '.mp4')
        ]
    )

def run():
    # shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    # os.makedirs(OUTPUT_DIR, exist_ok=True)
    # make_keyframes()
    make_movie()


if __name__ == "__main__":
    run()