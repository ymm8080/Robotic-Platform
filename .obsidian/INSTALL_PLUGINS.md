# Obsidian Plugin Installation Guide - EWM Robotic Platform

## 🚀 Quick Start

### Prerequisites
1. **Open Your Vault**: Launch Obsidian → "Open folder as vault" → Select `d:\EWM Robot\Robotic Platform Codes`
2. **Enable Community Plugins**: Settings → Community Plugins → "Turn on community plugins" (if not already enabled)

---

## 📦 Essential Plugins (Install These First)

### 1. **Dataview** ⭐ MUST HAVE
**What it does**: Query your notes like a database, create dynamic tables/lists

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Dataview`
3. Click "Install" → "Enable"

**Configuration**:
- Settings → Dataview
- Enable "Enable JavaScript Queries" (optional, for advanced queries)
- Enable "Pretty Print Tables" (recommended)

**Example Usage**:
````markdown
```dataview
TABLE status, date_created
FROM "01_architecture/decisions"
SORT file.name ASC
```
````

---

### 2. **Templater** ⭐ MUST HAVE
**What it does**: Advanced templates with variables, functions, and automation

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Templater`
3. Click "Install" → "Enable"

**Configuration**:
1. Settings → Templater
2. Set "Template folder location" to: `templates`
3. Enable "Trigger Templater on new file creation"
4. Set "Date format" to: `YYYY-MM-DD`
5. Set "Time format" to: `HH:mm`

**Key Features**:
- `{{date:YYYY-MM-DD}}` - Auto-insert today's date
- `{{time:HH:mm}}` - Auto-insert current time
- `{{title}}` - Current note title
- `<% tp.file.creation_date() %>` - File creation timestamp

**Example**: Create a new note using templates:
1. Navigate to any folder
2. Press `Ctrl+P` → Type "Templater: Insert template"
3. Select: "ADR Template", "Component Documentation Template", etc.

---

### 3. **Obsidian Git** ⭐ MUST HAVE
**What it does**: Auto-sync your vault with Git

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Obsidian Git`
3. Click "Install" → "Enable"

**Configuration**:
1. Settings → Obsidian Git
2. Set "Git repository path" to: `d:\EWM Robot\Robotic Platform Codes`
3. Enable "Commit on save" (recommended for auto-backup)
4. Set "Auto backup interval" to: `5` (minutes)
5. Enable "Push on backup" (if you have a remote repo)

**Manual Usage**:
- `Ctrl+P` → "Git: Commit all changes"
- `Ctrl+P` → "Git: Push"
- `Ctrl+P` → "Git: Pull"

---

### 4. **Excalidraw** ⭐ RECOMMENDED
**What it does**: Hand-drawn style diagrams, flowcharts, whiteboarding

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Excalidraw`
3. Click "Install" → "Enable"

**Configuration**:
1. Settings → Excalidraw
2. Set "Drawing folder" to: `assets/diagrams`
3. Enable "Use advanced tags" (optional)

**Usage**:
- `Ctrl+P` → "Excalidraw: New drawing"
- Double-click any `.excalidraw` file to edit
- Embed in notes: `![[diagram.excalidraw]]`

**Perfect for**:
- Architecture diagrams
- System flowcharts
- Robot path planning
- Network topology

---

### 5. **Kanban** ⭐ RECOMMENDED
**What it does**: Project management boards (like Trello)

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Kanban`
3. Click "Install" → "Enable"

**Configuration**:
- No special configuration needed
- Create boards in any folder

**Usage**:
1. Create new file: `Project Board.md`
2. Add kanban code block:

````markdown
```kanban
# Project Board

## Backlog
- [ ] Document MQTT architecture
- [ ] Create SAP integration guide

## In Progress
- [ ] Configure Node-RED flows

## Done
- [x] Install Obsidian
```
````

---

## 🔧 Recommended Plugins (Install As Needed)

### 6. **Calendar**
**What it does**: Calendar sidebar for daily notes

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Calendar`
3. Click "Install" → "Enable"

**Configuration**:
- Settings → Calendar
- Enable "Start week on Monday" (optional)

**Usage**:
- Click calendar icon in right sidebar
- Click any date to create/open daily note

---

### 7. **Periodic Notes**
**What it does**: Weekly, monthly, quarterly notes

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Periodic Notes`
3. Click "Install" → "Enable"

**Configuration**:
1. Settings → Periodic Notes
2. Set "Weekly note folder" to: `06_meetings`
3. Set "Monthly note folder" to: `06_meetings`
4. Set templates for each periodicity

**Usage**:
- `Ctrl+P` → "Open weekly note"
- `Ctrl+P` → "Open monthly note"

---

### 8. **Mind Map**
**What it does**: Visual mind maps from your notes

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Mind Map`
3. Click "Install" → "Enable"

**Usage**:
- Open any note
- `Ctrl+P` → "Mind Map: Open mind map"
- See connections visually

---

### 9. **Tag Wrangler**
**What it does**: Advanced tag management, renaming, merging

**Installation**:
1. Settings → Community Plugins → Browse
2. Search: `Tag Wrangler`
3. Click "Install" → "Enable"

**Usage**:
- Right-click any tag → "Rename tag"
- Merge duplicate tags
- See tag usage statistics

---

## 🎯 Installation Priority

### Phase 1: Immediate (Do Now)
- [ ] Dataview
- [ ] Templater
- [ ] Obsidian Git

### Phase 2: This Week
- [ ] Excalidraw
- [ ] Kanban

### Phase 3: As Needed
- [ ] Calendar
- [ ] Periodic Notes
- [ ] Mind Map
- [ ] Tag Wrangler

---

## 🔍 Troubleshooting

### Issue: "Community plugins" button is greyed out
**Solution**: 
1. Go to Settings → Community Plugins
2. Click "Restricted mode" toggle to turn it OFF
3. Restart Obsidian

### Issue: Plugin not showing in search
**Solution**:
1. Check internet connection
2. Click "Refresh" button in Community Plugins
3. Try searching with partial name (e.g., "data" instead of "dataview")

### Issue: Plugin not working after install
**Solution**:
1. Check if plugin is "Enabled" (toggle switch)
2. Restart Obsidian
3. Check plugin settings for required configuration

### Issue: Templater not inserting variables
**Solution**:
1. Verify template folder is set to `templates`
2. Enable "Trigger Templater on new file creation"
3. Use correct syntax: `{{date:YYYY-MM-DD}}` not `{{date}}`

---

## 📚 Plugin-Specific Tips

### Dataview Queries
```dataview
# List all ADRs with status
TABLE status, date_created
FROM "01_architecture/decisions"
WHERE contains(tags, "adr")
SORT file.name ASC
```

```dataview
# Recent troubleshooting issues
TABLE status, date_created
FROM "07_troubleshooting"
SORT date_created DESC
LIMIT 10
```

### Excalidraw Tips
- Use for architecture diagrams
- Export as PNG/PDF for presentations
- Link to notes: `[[Note Name]]` inside drawings
- Embed in notes: `![[drawing.excalidraw|800]]`

### Templater Templates
Create custom templates in `templates/` folder:
```markdown
---
created: {{date:YYYY-MM-DD}}
tags: [meeting]
---

# Meeting: {{title}}

## Attendees
- 

## Agenda
1. 

## Decisions
- 

## Action Items
- [ ] 
```

---

## 🎓 Next Steps

1. **Install Phase 1 plugins** (Dataview, Templater, Obsidian Git)
2. **Test templates**: Create a new note and apply a template
3. **Configure auto-backup**: Set up Obsidian Git for auto-sync
4. **Explore**: Try creating diagrams with Excalidraw
5. **Build your knowledge graph**: Start linking notes with `[[ ]]`

---

## 💡 Pro Tips

1. **Use Hotkeys**: Settings → Hotkeys → Customize for faster workflow
2. **Enable Graph View**: See how notes connect visually
3. **Use Daily Notes**: Perfect for meeting notes and logs
4. **Tag Everything**: Use `#robotics`, `#architecture`, `#deployment`, etc.
5. **Link Liberally**: Use `[[ ]]` to connect related concepts
6. **Backup Regularly**: Obsidian Git auto-sync to GitHub/GitLab

---

## 📖 Additional Resources

- [Obsidian Plugin Documentation](https://help.obsidian.md/Extending+Obsidian/Community+plugins)
- [Dataview Documentation](https://blacksmithgu.github.io/obsidian-dataview/)
- [Templater Documentation](https://silentvoid13.github.io/Templater/)
- [Excalidraw Documentation](https://github.com/zsviczian/obsidian-excalidraw-plugin)
- [Obsidian Git Documentation](https://github.com/denolehov/obsidian-git)

---

**Need help?** Check the [Obsidian Quick Start Guide.md](Obsidian%20Quick%20Start%20Guide.md) for general vault usage!
