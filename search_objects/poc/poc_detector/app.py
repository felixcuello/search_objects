import gradio as gr
import spaces

import detector

# On ZeroGPU the model must be loaded at startup, outside any @spaces.GPU function.
detector.get_detector()


@spaces.GPU
def detect_objects(image, threshold):
    if image is None:
        raise gr.Error("Debe subir una imagen para continuar.")

    objects = detector.detect_objects(image, threshold)
    annotations = [
        ((o["box"]["xmin"], o["box"]["ymin"], o["box"]["xmax"], o["box"]["ymax"]), o["label"])
        for o in objects
    ]
    return objects, (image, annotations)


demo = gr.Interface(
    fn=detect_objects,
    inputs=[
        gr.Image(type="pil", label="Imagen"),
        gr.Slider(0.05, 0.9, value=detector.DEFAULT_THRESHOLD, step=0.05, label="Umbral de confianza"),
    ],
    outputs=[
        gr.JSON(label="Objetos detectados"),
        gr.AnnotatedImage(label="Vista previa"),
    ],
    title="Detección de muebles y objetos",
    description="Suba una imagen de un ambiente para identificar muebles y objetos.",
)

if __name__ == "__main__":
    demo.launch()
