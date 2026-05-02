# Indeed Job Navigator Extension

A Chrome extension that automates navigation through Indeed job listings.

## How to Load the Extension in Chrome

1. **Open Chrome Extensions Page**
   - Open Google Chrome
   - Navigate to `chrome://extensions/`
   - Or click the three dots menu (⋮) → More Tools → Extensions

2. **Enable Developer Mode**
   - Toggle the "Developer mode" switch in the top right corner

3. **Load the Extension**
   - Click the "Load unpacked" button
   - Navigate to this directory: `/Users/iyuvchenko/tw/chrome_extension`
   - Click "Select" or "Open"

4. **Test the Extension**
   - Navigate to https://www.indeed.com/ in Chrome
   - You should see a blue control panel in the top-right corner
   - Click "Start" to begin automated navigation
   - Click "Stop" to pause the automation

## How to See Updates After Editing Files

When you edit any file in the extension:

1. **Save your changes** to the file (popup.html, popup.js, manifest.json, etc.)

2. **Reload the extension** in Chrome:
   - Go to `chrome://extensions/`
   - Find your extension
   - Click the reload icon (🔄) on the extension card

3. **Test your changes**:
   - Close the popup if it's open
   - Click the extension icon again to see your updates

### Quick Reload Shortcut
- You can also use the keyboard shortcut while on the `chrome://extensions/` page
- Or right-click the extension icon → "Manage Extension" → Click reload

## Files in This Extension

- `manifest.json` - Extension configuration and permissions
- `content.js` - Main script injected into Indeed pages
- `content.css` - Styling for the control panel
- `popup.html` - The HTML for the popup interface (optional)
- `popup.js` - JavaScript for the popup
- `icon*.svg` - Extension icons

## How It Works

The extension injects a control panel into Indeed.com pages with:
- **Start Button** - Begins automated clicking through job listings
- **Stop Button** - Stops the automation
- **Click Counter** - Shows how many times elements were clicked
- **Status Indicator** - Shows current state (Stopped/Running/Error)

The script will click on the element at XPath: `/html/body/main/div/div/div[2]/div/div[5]/div/div[1]/nav/ul/li[3]`

If that element isn't found, it will try to find alternative "Next" buttons.

## Customizing the Script

Edit `content.js` to:
- Change the XPath target (line 68)
- Adjust click interval (line 49, default: 2000ms = 2 seconds)
- Modify the navigation logic
- Add more features

After editing, reload the extension and refresh the Indeed page to see changes.
