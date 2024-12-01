# main.py

import os
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, ConcatDataset
from transformers import CLIPProcessor
from dataset import SkinLesionDataset
from model import CLIPFineTuner
from train import train_model
from evaluate import evaluate_model
from torchvision import transforms
from tqdm import tqdm

def main():
    # Paths and parameters
    data_dir = '/data/huzhengyu/github_repo/tony_csml/csml-final-project/split_data'
    original_train_dir = os.path.join(data_dir, 'train')
    augmented_train_dir = os.path.join(data_dir, 'augmented_train')
    validation_dir = os.path.join(data_dir, 'validation')
    test_dir = os.path.join(data_dir, 'test')

    batch_size = 16
    num_epochs = 20
    num_workers = 8  # Adjust based on your system
    learning_rate = 1e-5
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

    # Define transformations
    # Transformations for original training images (with augmentation)
    train_transform = transforms.Compose([
        # Geometric Transformations
        transforms.RandomRotation(degrees=30),
        transforms.RandomHorizontalFlip(p=0.5),
        transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
        transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),

        # Color Transformations
        transforms.ColorJitter(
            brightness=0.2,
            contrast=0.2,
            saturation=0.2,
            hue=0.05
        ),

        # Convert to Tensor
        transforms.ToTensor(),

        # Noise Addition (apply with 50% probability)
        transforms.RandomApply([
            transforms.Lambda(lambda img: torch.clamp(img + torch.randn_like(img) * 0.01, 0, 1))
        ], p=0.5),

        # Normalize using CLIP's mean and std
        transforms.Normalize(mean=mean, std=std),
    ])

    # Transformations for augmented training images (already augmented, minimal transforms)
    augmented_train_transform = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])

    # Transformations for validation and test sets (no augmentation)
    val_test_transform = transforms.Compose([
        transforms.Resize(224),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(mean=mean, std=std),
    ])

    # Create datasets
    # Original training dataset with augmentation
    original_train_dataset = SkinLesionDataset(
        image_dir=original_train_dir,
        classes=classes,
        processor=processor,
        transform=train_transform
    )

    # Augmented training dataset without additional augmentation
    augmented_train_dataset = SkinLesionDataset(
        image_dir=augmented_train_dir,
        classes=classes,
        processor=processor,
        transform=augmented_train_transform
    )

    # Combine original and augmented training datasets
    combined_train_dataset = ConcatDataset([original_train_dataset, augmented_train_dataset])

    # Validation and Test datasets
    val_dataset = SkinLesionDataset(
        image_dir=validation_dir,
        classes=classes,
        processor=processor,
        transform=val_test_transform
    )

    test_dataset = SkinLesionDataset(
        image_dir=test_dir,
        classes=classes,
        processor=processor,
        transform=val_test_transform
    )

    # Create dataloaders
    dataloaders = {
        'train': DataLoader(original_train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers),
        'validation': DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers),
        'test': DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    }

    dataset_sizes = {
        'train': len(original_train_dataset),
        'validation': len(val_dataset),
        'test': len(test_dataset)
    }

    print(f"Dataset sizes: {dataset_sizes}")

    # Initialize the model
    model = CLIPFineTuner(num_classes=num_classes).to(device)

    # Define loss function and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate)

    # Train the model
    model = train_model(model, dataloaders, dataset_sizes, criterion, optimizer, device, num_epochs=num_epochs)

    # Evaluate the model
    evaluate_model(model, dataloaders['test'], device, classes)

    # Save the model
    torch.save(model.state_dict(), 'clip_finetuned_model_v2.pth')
    print('Model saved to clip_finetuned_model.pth')

if __name__ == '__main__':
    main()