import torch
from ultralytics import YOLO
from pathlib import Path
import time
import numpy as np

def load_model(model_path):
    return YOLO(model_path)

def test_accuracy(model, test_loader, iou_thresholds=[0.5, 0.7, 0.9]):
    results = []
    for iou_thresh in iou_thresholds:
        metrics = model.val(data=test_loader, iou=iou_thresh)
        results.append({
            'iou_threshold': iou_thresh,
            'mAP': metrics.box.map,
            'precision': metrics.box.p,
            'recall': metrics.box.r
        })
    return results

def test_speed(model, test_loader):
    start_time = time.time()
    model(next(iter(test_loader))[0])  # Warm-up run
    
    times = []
    for images, _ in test_loader:
        torch.cuda.synchronize()
        start = time.time()
        model(images)
        torch.cuda.synchronize()
        end = time.time()
        times.append(end - start)
    
    avg_time = np.mean(times)
    fps = 1 / avg_time
    return {'avg_inference_time': avg_time, 'fps': fps}

def test_robustness(model, robustness_loader):
    results = model(robustness_loader)
    # Process results to get metrics for different conditions
    # This would depend on how your robustness_loader is structured
    return results

def main():
    model_path = 'runs/obb/tRRE/weights/best.pt'
    test_data = 'C:/Code/porject3/tree_detection.yaml'
    robustness_data = 'C:/Code/porject3/tree_detection.yaml'

    model = load_model(model_path)

    # Load test data
    test_loader = model.DataLoader(test_data, batch_size=1, shuffle=False)
    robustness_loader = model.DataLoader(robustness_data, batch_size=1, shuffle=False)

    # Run tests
    accuracy_results = test_accuracy(model, test_loader)
    speed_results = test_speed(model, test_loader)
    robustness_results = test_robustness(model, robustness_loader)

    # Print results
    print("Accuracy Results:")
    for result in accuracy_results:
        print(f"IoU: {result['iou_threshold']}, mAP: {result['mAP']}, Precision: {result['precision']}, Recall: {result['recall']}")

    print("\nSpeed Results:")
    print(f"Average Inference Time: {speed_results['avg_inference_time']:.4f} seconds")
    print(f"FPS: {speed_results['fps']:.2f}")

    print("\nRobustness Results:")
    # Process and print robustness results

if __name__ == "__main__":
    main()