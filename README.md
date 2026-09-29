# Federated Learning Setup with Akida on Raspberry Pi 5

This repository demonstrates a lightweight Federated Learning (FL) setup using neuromorphic AI models deployed on BrainChip Akida PCIe accelerators paired with Raspberry Pi 5 devices. It provides scripts for a centralized Flask server to receive model weight updates and a client script to upload Akida model weights via HTTP.

## Overview

Neuromorphic models trained on individual RPI5-Akida nodes can contribute updates to a shared model hosted on a central server. This setup simulates a federated learning architecture for edge AI applications that require privacy, low latency, and energy efficiency.

## Repository Structure

```
├── federated_learning_server.py       # Flask server to receive model weights
├── federated_learning_client.py       # Client script to upload Akida model weights
├── model_utils.py                     # (Optional) Placeholder for weight handling utilities
├── model_training.py                  # (Optional) Placeholder for training-related code
└── README.md
```

## Requirements

- Python 3.7+
- Flask
- NumPy
- Requests
- Akida Python SDK (required on client device)

Install the dependencies using:

```bash
pip install flask numpy requests
```

## Getting Started

### 1. Launch the Federated Learning Server

On a device intended to act as the central server:

```bash
python3 federated_learning_server.py
```

The server will listen for HTTP POST requests on port `5000` and respond to updates sent to the `/upload` endpoint.

### 2. Configure and Run the Client

On each RPI5-Akida node:

- Ensure the Akida model has been trained.
- Replace the `SERVER_IP` variable inside `federated_learning_client.py` with the IP address of the server.
- Run the script:

```bash
python3 federated_learning_client.py
```

This will extract the weights from the Akida model and transmit them to the server in JSON format.

## Example Response

After a successful POST:

```
Model weights uploaded successfully.
```

If an error occurs (e.g., connection refused or malformed weights), you will see an appropriate status message.

## Security Considerations

This is a prototype-level setup for research. For real-world deployment:
- Use HTTPS instead of HTTP.
- Authenticate clients using tokens or API keys.
- Validate the format and shape of model weights before acceptance.

## Acknowledgements

This implementation is part of a broader effort to demonstrate low-cost, energy-efficient neuromorphic AI for distributed and networked edge environments, particularly leveraging the BrainChip Akida PCIe board and Raspberry Pi 5 hardware.

