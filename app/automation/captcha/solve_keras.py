import sys
import base64
import numpy as np
import tensorflow as tf
import keras

CHARS = [str(d) for d in range(10)]
BLANK_INDEX = len(CHARS) # 10

def decode_predictions(pred, chars):
    pred_time_major = tf.transpose(pred, perm=[1, 0, 2])
    input_len = np.ones(pred.shape[0]) * pred.shape[1]
    decoded, log_prob = tf.nn.ctc_greedy_decoder(
        pred_time_major, 
        sequence_length=tf.cast(input_len, tf.int32), 
        blank_index=BLANK_INDEX
    )
    sparse_tensor = decoded[0]
    dense_decoded = tf.sparse.to_dense(sparse_tensor, default_value=-1).numpy()
    output_numbers = []
    for res in dense_decoded:
        digits = [chars[int(c)] for c in res if c != -1]
        reversed_str = "".join(digits)
        normal_str = reversed_str[::-1]
        output_numbers.append(normal_str if normal_str != "" else "?")
    return output_numbers

def solve_image_data(img_bytes: bytes, model) -> str:
    image_decoded = tf.io.decode_image(img_bytes, channels=3)
    image_resized = tf.image.resize(image_decoded, [25, 180])
    image_normalized = tf.cast(image_resized, tf.float32) / 255.0
    input_tensor = np.expand_dims(image_normalized.numpy(), axis=0)
    
    # Run prediction
    pred = model.predict(input_tensor, verbose=0)
    
    # Decode predictions
    decoded = decode_predictions(pred, CHARS)
    return decoded[0]

def main():
    if len(sys.argv) < 3:
        print("Usage: solve_keras.py <model_path> <image_base64_or_file_path>")
        sys.exit(1)
        
    model_path = sys.argv[1]
    image_input = sys.argv[2]
    
    try:
        # Load keras model (compile=False for fast loading & no custom objects needed)
        model = keras.models.load_model(model_path, compile=False)
    except Exception as e:
        print(f"Error loading model: {e}", file=sys.stderr)
        sys.exit(1)
        
    try:
        if image_input == "-":
            # Read base64 from stdin
            b64_data = sys.stdin.read().strip()
            # Clean up potential headers (e.g. data:image/png;base64,...)
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            img_bytes = base64.b64decode(b64_data)
        elif image_input.startswith("data:image/") or len(image_input) > 256:
            # Direct base64 string
            b64_data = image_input
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            img_bytes = base64.b64decode(b64_data)
        else:
            # File path
            img_bytes = tf.io.read_file(image_input).numpy()
            
        result = solve_image_data(img_bytes, model)
        print(result)
    except Exception as e:
        print(f"Error during prediction: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
