# evaluate_clip_model.py

import os
import torch
import torch.nn as nn
from torchvision import transforms
from torch.utils.data import DataLoader
from transformers import CLIPProcessor
from PIL import Image
from torch.utils.data import Dataset
from sklearn.metrics import classification_report, confusion_matrix, precision_score, recall_score, f1_score
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
from model import CLIPModel

# Define Dataset
class SkinLesionDataset(Dataset):
    def __init__(self, image_dir, classes, processor, transform=None):
        self.image_dir = image_dir
        self.classes = classes
        self.processor = processor
        self.transform = transform
        self.image_paths = []
        self.labels = []

        for idx, cls in enumerate(self.classes):
            class_dir = os.path.join(self.image_dir, cls)
            if not os.path.isdir(class_dir):
                continue  # Skip if the class directory does not exist
            for img_name in os.listdir(class_dir):
                if img_name.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp', '.gif')):
                    self.image_paths.append(os.path.join(class_dir, img_name))
                    self.labels.append(idx)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        image = Image.open(self.image_paths[idx]).convert('RGB')
        label = self.labels[idx]

        if self.transform:
            image = self.transform(image)

        return image, label

# Define Model
class CLIPFineTuner(nn.Module):
    def __init__(self, num_classes):
        super(CLIPFineTuner, self).__init__()
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
        # Freeze the text encoder and language projection layers
        for param in self.clip_model.text_model.parameters():
            param.requires_grad = False
        self.clip_model.logit_scale.requires_grad = False
        self.clip_model.text_projection.requires_grad = False

        # Replace the image projection head with a classification head
        self.classifier = nn.Linear(self.clip_model.config.projection_dim, num_classes)

    def forward(self, pixel_values):
        image_embed = self.clip_model.vision_model(pixel_values=pixel_values).pooler_output
        image_embed = self.clip_model.visual_projection(image_embed)
        logits = self.classifier(image_embed)
        return logits

# Evaluation function
def evaluate_model(model, dataloader, device, class_names):
    model.eval()
    criterion = nn.CrossEntropyLoss()
    running_loss = 0.0
    running_corrects = 0

    all_preds = []
    all_labels = []

    with torch.no_grad():
        for inputs, labels in tqdm(dataloader):
            inputs = inputs.to(device)
            labels = labels.to(device)

            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            loss = criterion(outputs, labels)

            running_loss += loss.item() * inputs.size(0)
            running_corrects += torch.sum(preds == labels.data)

            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

    total_loss = running_loss / len(dataloader.dataset)
    total_acc = running_corrects.double() / len(dataloader.dataset)

    print(f'Test Loss: {total_loss:.4f} Acc: {total_acc:.4f}')

    # Additional metrics
    precision = precision_score(all_labels, all_preds, average='weighted')
    recall = recall_score(all_labels, all_preds, average='weighted')
    f1 = f1_score(all_labels, all_preds, average='weighted')

    print(f'Precision: {precision:.4f} Recall: {recall:.4f} F1-Score: {f1:.4f}')

    # Classification Report
    print('Classification Report:')
    print(classification_report(all_labels, all_preds, target_names=class_names))

    # Confusion Matrix (Normalized)
    cm = confusion_matrix(all_labels, all_preds, normalize='true')
    plt.figure(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt='.2f', cmap='Blues',
                xticklabels=class_names, yticklabels=class_names)
    plt.ylabel('Actual')
    plt.xlabel('Predicted')
    plt.title('Normalized Confusion Matrix')

    # Save the confusion matrix
    plt.savefig('confusion_matrix_clip_finetuned_normalized.png')
    print("Confusion matrix saved to 'confusion_matrix_clip_finetuned_normalized.png'")
    plt.show()

# Main function
def main():
    # Paths and parameters
    data_dir = '/data/huzhengyu/github_repo/tony_csml/csml-final-project/split_data'
    test_dir = os.path.join(data_dir, 'test')
    batch_size = 16
    num_workers = 8  # Adjust based on your system
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f'Using device: {device}')

    # Classes
    classes = ['akiec', 'bcc', 'bkl', 'df', 'mel', 'nv', 'vasc']
    num_classes = len(classes)
    print(f"Classes: {classes}")

    # Processor
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")

    # Define mean and std for normalization (using CLIP's defaults)
    mean = processor.image_processor.image_mean
    std = processor.image_processor.image_std

    # Transformations for test set
    val_test_transform = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])

    # Test dataset
    test_dataset = SkinLesionDataset(
        image_dir=test_dir,
        classes=classes,
        processor=processor,
        transform=val_test_transform
    )

    # Test DataLoader
    test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)

    # Load the model
    model = CLIPFineTuner(num_classes=num_classes)
    model.load_state_dict(torch.load('clip_finetuned_model_v2.pth'))
    model = model.to(device)
    print('Model loaded from clip_finetuned_model_v2.pth')

    # Evaluate the model
    evaluate_model(model, test_loader, device, classes)

if __name__ == '__main__':
    main()
