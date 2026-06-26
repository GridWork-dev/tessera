import { createFileRoute } from '@tanstack/react-router';
import { SettingsView } from '../components/SettingsView';

/**
 * Settings route — hosts the Settings → License panel (Spec J). Standard in-app
 * chrome (the SettingsView renders the shared command bar + nav).
 */
export const Route = createFileRoute('/settings')({ component: SettingsView });
