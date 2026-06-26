import { useNavigate } from '@tanstack/react-router';
import { Command } from 'cmdk';
import { useState } from 'react';
import { useCollections } from '../hooks/queries';
import { openDocs } from '../lib/docs';
import { RATINGS, ratingLabel } from '../lib/rating';
import { useWorkspace } from '../store/useWorkspace';
import * as c from './CommandPalette.css';

/**
 * ⌘K command palette — composes the existing useWorkspace actions (search,
 * rating, sort, status, density, collections) + saved searches/views, so every
 * keyboard-first action has one discoverable home. Opened from Browse's ⌘K
 * handler via the `commandOpen` store flag.
 */
export function CommandPalette() {
  const open = useWorkspace((s) => s.commandOpen);
  const setOpen = useWorkspace((s) => s.setCommandOpen);
  const [search, setSearch] = useState('');

  const setQuery = useWorkspace((s) => s.setQuery);
  const setRating = useWorkspace((s) => s.setRating);
  const setSort = useWorkspace((s) => s.setSort);
  const setProcessedFilter = useWorkspace((s) => s.setProcessedFilter);
  const setActiveCollectionId = useWorkspace((s) => s.setActiveCollectionId);
  const activeCollectionId = useWorkspace((s) => s.activeCollectionId);
  const toggleDensity = useWorkspace((s) => s.toggleDensity);
  const setInspectorOpen = useWorkspace((s) => s.setInspectorOpen);
  const inspectorOpen = useWorkspace((s) => s.inspectorOpen);
  const clearFilters = useWorkspace((s) => s.clearFilters);
  const savedViews = useWorkspace((s) => s.savedViews);
  const saveView = useWorkspace((s) => s.saveView);
  const applyView = useWorkspace((s) => s.applyView);
  const deleteView = useWorkspace((s) => s.deleteView);

  const navigate = useNavigate();
  const { data: collectionsData } = useCollections();
  const collections = collectionsData?.collections ?? [];

  // Run an action then close the palette + reset the typed query.
  const run = (fn: () => void) => {
    fn();
    setSearch('');
    setOpen(false);
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command menu"
      overlayClassName={c.overlay}
      contentClassName={c.dialog}
    >
      <Command.Input
        className={c.input}
        placeholder="Search assets or run a command…"
        value={search}
        onValueChange={setSearch}
      />
      <Command.List className={c.list}>
        <Command.Empty className={c.empty}>No matching commands.</Command.Empty>

        {search.trim() !== '' && (
          <Command.Group className={c.group} heading="Search">
            <Command.Item
              className={c.item}
              value={`search ${search}`}
              onSelect={() => run(() => setQuery(search.trim()))}
            >
              <span className={c.itemLabel}>Search images for “{search.trim()}”</span>
              <span className={c.itemMeta}>↵</span>
            </Command.Item>
          </Command.Group>
        )}

        <Command.Group className={c.group} heading="Go to">
          <Command.Item
            className={c.item}
            value="go browse"
            onSelect={() => run(() => navigate({ to: '/' }))}
          >
            <span className={c.itemLabel}>Browse</span>
          </Command.Item>
          <Command.Item
            className={c.item}
            value="go videos"
            onSelect={() => run(() => navigate({ to: '/videos' }))}
          >
            <span className={c.itemLabel}>Videos</span>
          </Command.Item>
          <Command.Item
            className={c.item}
            value="go dashboard"
            onSelect={() => run(() => navigate({ to: '/dashboard' }))}
          >
            <span className={c.itemLabel}>Dashboard</span>
          </Command.Item>
          <Command.Item
            className={c.item}
            value="go training"
            onSelect={() => run(() => navigate({ to: '/training' }))}
          >
            <span className={c.itemLabel}>Training mode</span>
          </Command.Item>
        </Command.Group>

        <Command.Group className={c.group} heading="Rating filter">
          {RATINGS.map((r) => (
            <Command.Item
              key={r}
              className={c.item}
              value={`rating ${r}`}
              onSelect={() => run(() => setRating(r))}
            >
              <span className={c.itemLabel}>Filter rating: {ratingLabel(r)}</span>
            </Command.Item>
          ))}
          <Command.Item
            className={c.item}
            value="rating clear"
            onSelect={() => run(() => setRating(null))}
          >
            <span className={c.itemLabel}>Clear rating filter</span>
          </Command.Item>
        </Command.Group>

        <Command.Group className={c.group} heading="Sort">
          {(['recent', 'random', 'relevance'] as const).map((srt) => (
            <Command.Item
              key={srt}
              className={c.item}
              value={`sort ${srt}`}
              onSelect={() => run(() => setSort(srt))}
            >
              <span className={c.itemLabel}>Sort: {srt}</span>
            </Command.Item>
          ))}
        </Command.Group>

        <Command.Group className={c.group} heading="Status">
          {(['all', 'tagged', 'untagged'] as const).map((st) => (
            <Command.Item
              key={st}
              className={c.item}
              value={`status ${st}`}
              onSelect={() => run(() => setProcessedFilter(st))}
            >
              <span className={c.itemLabel}>Status: {st}</span>
            </Command.Item>
          ))}
        </Command.Group>

        <Command.Group className={c.group} heading="View">
          <Command.Item
            className={c.item}
            value="toggle density"
            onSelect={() => run(toggleDensity)}
          >
            <span className={c.itemLabel}>Toggle grid density</span>
          </Command.Item>
          <Command.Item
            className={c.item}
            value="toggle inspector"
            onSelect={() => run(() => setInspectorOpen(!inspectorOpen))}
          >
            <span className={c.itemLabel}>{inspectorOpen ? 'Hide' : 'Show'} inspector</span>
          </Command.Item>
        </Command.Group>

        {collections.length > 0 && (
          <Command.Group className={c.group} heading="Collections">
            {collections.map((col) => (
              <Command.Item
                key={col.id}
                className={c.item}
                value={`collection ${col.name}`}
                onSelect={() => run(() => setActiveCollectionId(col.id))}
              >
                <span className={c.itemLabel}>{col.name}</span>
                <span className={c.itemMeta}>{col.image_count}</span>
              </Command.Item>
            ))}
            {activeCollectionId !== null && (
              <Command.Item
                className={c.item}
                value="collection clear"
                onSelect={() => run(() => setActiveCollectionId(null))}
              >
                <span className={c.itemLabel}>Clear collection filter</span>
              </Command.Item>
            )}
          </Command.Group>
        )}

        <Command.Group className={c.group} heading="Saved views">
          {savedViews.map((v) => (
            <Command.Item
              key={v.name}
              className={c.item}
              value={`view ${v.name}`}
              onSelect={() => run(() => applyView(v))}
            >
              <span className={c.itemLabel}>{v.name}</span>
              <span className={c.itemMeta}>apply</span>
            </Command.Item>
          ))}
          <Command.Item
            className={c.item}
            value="save current view"
            onSelect={() =>
              run(() => {
                const name = window.prompt('Save current filters as:')?.trim();
                if (name) saveView(name);
              })
            }
          >
            <span className={c.itemLabel}>Save current view…</span>
          </Command.Item>
          {savedViews.map((v) => (
            <Command.Item
              key={`del-${v.name}`}
              className={c.item}
              value={`delete view ${v.name}`}
              onSelect={() => run(() => deleteView(v.name))}
            >
              <span className={c.itemLabel}>Delete saved view: {v.name}</span>
            </Command.Item>
          ))}
        </Command.Group>

        <Command.Group className={c.group} heading="Filters">
          <Command.Item
            className={c.item}
            value="clear all filters"
            onSelect={() => run(clearFilters)}
          >
            <span className={c.itemLabel}>Clear all filters</span>
          </Command.Item>
        </Command.Group>

        <Command.Group className={c.group} heading="Help">
          <Command.Item
            className={c.item}
            value="open documentation"
            onSelect={() => run(() => void openDocs())}
          >
            <span className={c.itemLabel}>Open documentation</span>
          </Command.Item>
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
