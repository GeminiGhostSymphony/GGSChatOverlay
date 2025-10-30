const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const manifestPath = path.join(__dirname, '../../manifest.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

// Get the commit SHAs from the environment variables
const beforeSha = process.env.GITHUB_EVENT_BEFORE;
const afterSha = process.env.GITHUB_SHA;

// Get the changed files in the push
const changedFiles = execSync(`git diff --name-only ${beforeSha} ${afterSha}`).toString().trim().split('\n');

// Get the current timestamp for the new version
const timestamp = new Date().toISOString();

// Loop through changed files to find the relevant one
let changedFile = '';
for (const file of changedFiles) {
  if (file === 'global-badges.json') {
    manifest.global_badges.version = timestamp;
    changedFile = file;
    break; // Exit the loop since we found the global file
  }

  // Check if it's a channel badge file
  if (file.startsWith('channel-') && file.endsWith('-badges.json')) {
    const channelId = file.match(/channel-(.*)-badges.json/)[1];
    if (manifest.channels[channelId]) {
      manifest.channels[channelId].version = timestamp;
      changedFile = file;
    }
  }
}

// Update the global manifest version
manifest.version = timestamp;

// Write the updated manifest file back to the repository
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));

// Set an output to be used in the commit message
console.log(`::set-output name=changed_file::${changedFile}`);
