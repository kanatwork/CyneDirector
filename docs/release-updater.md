# GitHub release updater — accepted requirement and proposed contract

24 November 2026. Requested explicitly with the questionnaire answers.
**Status: accepted scope; not implemented or tested as an installed-app updater.**

## User outcome

An editor can discover a new CyneDirector release and update the installed app
without using Git, running setup commands or risking their media/project data.
The full application redesign must include this flow.

## Proposed experience

1. Offer automatic checks for new stable releases and a manual **Check for Updates**.
2. Show installed/new version, release notes, compatibility and download size.
3. Let the user download the compatible Mac/Windows build and install at a safe
   restart or quit. Do not interrupt processing, playback review or unsaved work.
4. Show clear download/install progress and recoverable failure states. Keep the
   current app usable if the download fails or a release has no compatible asset.
5. Keep beta/pre-release participation separate and optional.

These interaction details are recommendations for the design, not additional
questionnaire answers or an already functioning update service.

## Release source

Use versioned **published GitHub Releases** from `kanatwork/CyneDirector`, with
platform/architecture-specific installable assets and release metadata. GitHub
Releases associate tags, notes and downloadable assets; the release API exposes
the latest published release. [GitHub releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases),
[release API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release)

The development checkout has its own update workflow. A product updater must
preserve uncommitted development work and never overwrite it through an unattended
source-tree replacement. A source ZIP is not evidence of a tested installer.

The current checkout has no updater or release-build workflow located in this
review. Live GitHub release inventory was not verified because the release-page
fetch failed; do not infer from that that the remote has no releases.

## Data and execution safety

- Separate installed application files from user projects, original media, jobs,
  settings, source/output pins and model caches.
- Check available space, supported OS/architecture and release compatibility.
- Verify update authenticity/integrity before applying it; signing and platform
  packaging requirements must be part of the release pipeline.
- Finish/pause active jobs at safe boundaries and save pending edits before restart.
- Preserve a recoverable previous app version. If a release changes project schemas,
  stage a verified backup and an explicit migration/recovery path; old-app rollback
  alone cannot undo arbitrary data migrations.
- App updates and model/index upgrades are separate operations. A new release must
  not silently download new multi-GB weights or reprocess the entire library.
- A failed/cancelled/interrupted update must not mark work complete or remove
  existing user data.

## Delivery dependencies and acceptance

Choose the update implementation after the desktop framework/package strategy is
settled. Build and test the real Apple Silicon Mac and declared Windows artifacts,
not only a release-version notification in the source checkout.

Required tests include version ordering/stable-channel selection, unavailable
network, no compatible asset, insufficient space, failed verification, interrupted
download/install, active jobs/unsaved edits, restart, schema recovery and preservation
of existing projects/caches. Verify upgrading an actual installed older build on
both platforms, then reopening a real test project and resuming its pending work.

Implementation belongs to the redesigned product's release/delivery milestone.
This document does not claim that the current app can already update itself.
