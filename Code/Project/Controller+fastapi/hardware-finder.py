import pyudev

def list_usb_devices_like_lsusb():
    context = pyudev.Context()
    devices = []

    for device in context.list_devices(subsystem='usb', DEVTYPE='usb_device'):
        bus = device.device_path.split('/')[-2].replace('usb', '').zfill(3)
        devnum = device.get('DEVNUM', '000').zfill(3)
        vid = device.get('ID_VENDOR_ID', '0000')
        pid = device.get('ID_MODEL_ID', '0000')
        vendor = device.get('ID_VENDOR', 'Unknown Vendor')
        product = device.get('ID_MODEL', 'Unknown Product')
        devices.append(f"Bus {bus} Device {devnum}: ID {vid}:{pid} {vendor} {product}")

    return sorted(devices)

# Example usage:
for line in list_usb_devices_like_lsusb():
    print(line)

