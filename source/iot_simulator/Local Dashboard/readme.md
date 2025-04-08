# Local Dashboard

The dashboard is a Python–Qt application that interacts with AWS IoT Core via the AWS IoT Data API. To run it, the user system must have:

### **Python Environment and Dependencies:**

    * A supported version of Python (e.g., Python 3.6+).
    * Required Python packages installed (such as boto3, certifi, and PyQt5).
    * Access to a graphical environment (since it uses PyQt5).

### **AWS Credentials and Permissions:**

    * Valid AWS credentials configured on the system (via environment variables, AWS credentials file, or IAM role) that grant permission to perform operations on the IoT Data service.
    * Specifically, the IAM policy should allow actions such as:
        * `iot:GetThingShadow`
        * `iot:UpdateThingShadow`
        * `iot:Publish` (if the dashboard sends commands)
            These permissions enable the dashboard to retrieve and update thing shadows and to publish messages.

### **Network Connectivity:**

    * The system must be able to make outbound HTTPS connections to the AWS IoT endpoints (with certificate verification via certifi).



### The dashboard accepts two command-line options:

* **--device-prefix**: A string that sets the prefix for device names (default is `"aircon"`).
* **--count**: An integer that specifies how many devices to generate (default is `2`).

For example, you could run:

```
python dashboard.py --device-prefix myDevice --count 5
```


