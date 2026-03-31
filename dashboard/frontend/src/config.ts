/**
 * Dashboard configuration — external links and global settings.
 * Edit this file to change which resources appear in the sidebar.
 */

export interface ExternalLink {
  label: string
  url: string
  icon: 'Sheet' | 'FolderOpen' | 'ExternalLink'
  enabled: boolean
}

export const EXTERNAL_LINKS: ExternalLink[] = [
  {
    label: 'Google Sheet',
    url: 'https://docs.google.com/spreadsheets/d/15OI-dwZBCpag7K_Gif1GcAampoou9pqFHVohjcHKpIc',
    icon: 'Sheet',
    enabled: true,
  },
  {
    label: 'Drive Folder',
    url: 'https://drive.google.com/drive/folders/1example',
    icon: 'FolderOpen',
    enabled: false,
  },
]
