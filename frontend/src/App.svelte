<script>
  import { Button, Card, Checkbox, Select, TextField } from '@monos/ui';
  let on = false;
</script>

<Card>
  <TextField label="Smoke test" placeholder="type here" />
  <Select label="Smoke select" options={[{ value: 'a', label: 'Option A' }]} value="a" />
  <Checkbox bind:checked={on} label="Smoke checkbox" />
  <Button>Start</Button>
</Card>
