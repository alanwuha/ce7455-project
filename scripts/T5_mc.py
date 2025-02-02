from transformers import T5PreTrainedModel, T5Config, \
    T5_PRETRAINED_MODEL_ARCHIVE_MAP, T5Model, T5ForConditionalGeneration
from torch.nn import CrossEntropyLoss, Linear
import torch
import torch.nn as nn
from torch.utils.checkpoint import checkpoint, checkpoint_sequential


class T5ForMultipleChoice(T5PreTrainedModel):
    config_class = T5Config
    pretrained_model_archive_map = T5_PRETRAINED_MODEL_ARCHIVE_MAP
    base_model_prefix = "t5"

    def __init__(self, config):
        super().__init__(config)
        
        self.save_mem = config.save_mem
        # self.t5 = T5ForConditionalGeneration(config)
        if self.save_mem:
            self.dummy_tensor = torch.ones(1, dtype=torch.float32, requires_grad=True)
            self.t5_wrapped = ModuleWrapperIgnores2ndArg(T5ForConditionalGeneration(config))
        else:
            self.t5 = self.t5_wrapped = T5ForConditionalGeneration(config)
            
        
        #choose to use hidden states or softmaxed values for classification? currently softmaxed_values
        # self.classifier = Linear(int((config.max_seq_len/2)-1), 1)
 
        self.init_weights()

    def forward(self, kwargs):
        
        
        labels = kwargs.pop('labels', None)
        lm_labels = kwargs.pop('lm_labels', None)
        eos_token_id = kwargs.pop('eos_token_id')
    
        
        if lm_labels is not None: #if no mcq labels, do causal language modeling training model
            bs, seq_len = kwargs['input_ids'].shape
            decoder_input_ids = self._shift_right(lm_labels)
            
            kwargs['decoder_attention_mask'][:,1:] = kwargs['decoder_attention_mask'][:,:-1].clone()
            kwargs['decoder_attention_mask'][:,0] = 1
            
            # print("kwargs['input_ids']", kwargs['input_ids'])
            # print("kwargs['attention_mask']", kwargs['attention_mask'])
            # print('decoder_input_ids', decoder_input_ids)
            # print('decoder_attention_mask', kwargs['decoder_attention_mask'])
            # print('lm_labels', lm_labels)
            # input()
            if self.save_mem:
                outputs = checkpoint(self.t5_wrapped, kwargs['input_ids'], kwargs['attention_mask'],\
                                 decoder_input_ids , kwargs['decoder_attention_mask'], lm_labels, self.dummy_tensor)
                # loss_fct = CrossEntropyLoss(ignore_index=-100)
                # loss = loss_fct(outputs[0].view(-1, outputs[0].size(-1)), lm_labels.view(-1))
                # outputs = (loss,) + outputs  

            else:
                outputs = self.t5(input_ids=kwargs['input_ids'], attention_mask=kwargs['attention_mask'], \
                                 decoder_input_ids=decoder_input_ids ,decoder_attention_mask=kwargs['decoder_attention_mask'], \
                                lm_labels=lm_labels)
            return outputs
        
        bs, num_choices, seq_len = kwargs['input_ids'].shape    
        kwargs['input_ids'] = kwargs['input_ids'].view(-1, kwargs['input_ids'].size(-1))
        kwargs['attention_mask'] = kwargs['attention_mask'].view(-1, kwargs['attention_mask'].size(-1))
        kwargs['decoder_input_ids'] = kwargs['decoder_input_ids'].view(-1, kwargs['decoder_input_ids'].size(-1))
        kwargs['decoder_attention_mask'] = kwargs['decoder_attention_mask'].view(-1, kwargs['decoder_attention_mask'].size(-1))
        #assuming bos is pad == 0
        shift_labels = kwargs['decoder_input_ids'] #shift labels are the predictions from the lm
        kwargs['decoder_input_ids'] = self._shift_right(kwargs['decoder_input_ids'])
        kwargs['decoder_attention_mask'][:,1:] = kwargs['decoder_attention_mask'][:,:-1].clone()
        kwargs['decoder_attention_mask'][:,0] = 1
        if self.save_mem:
            decoder_outputs,encoder_outputs = checkpoint(self.t5_wrapped, kwargs['input_ids'], kwargs['attention_mask'],\
                             kwargs['decoder_input_ids'] , kwargs['decoder_attention_mask'], None, self.dummy_tensor)
        else:
            decoder_outputs,encoder_outputs = self.t5(input_ids=kwargs['input_ids'], attention_mask=kwargs['attention_mask'],\
                                decoder_input_ids=kwargs['decoder_input_ids'], decoder_attention_mask=kwargs['decoder_attention_mask'])
        
        
        #currently using probability -softmaxed values of each time step for prediction
        eos_idxs = (shift_labels==eos_token_id).nonzero()
        softmaxed_probs = decoder_outputs.softmax(dim=-1)
        
        pred = torch.argmax(softmaxed_probs,axis=-1)
        
        #take indices of each time step
        seq_probs = softmaxed_probs[torch.arange(bs*num_choices).unsqueeze(1),torch.arange(seq_len), shift_labels]
        for eos_idx in eos_idxs:
            seq_probs[eos_idx[0],eos_idx[1]+1:] = 1.0
        seq_probs = seq_probs.prod(dim=-1)    
        reshaped_probs = seq_probs.view(bs, num_choices)
        outputs = (reshaped_probs, decoder_outputs, encoder_outputs)  # add hidden states and attention if they are here
        if labels is not None:
            loss_fct = CrossEntropyLoss()
            loss = loss_fct(reshaped_probs, labels)
            outputs = (loss,) + outputs

        return outputs  # (loss), reshaped_logits, (hidden_states), (attentions)



class ModuleWrapperIgnores2ndArg(nn.Module):
    def __init__(self, module):
        super().__init__()
        self.module = module

    def forward(self, input_ids, attention_mask, decoder_input_ids, decoder_attention_mask, lm_labels, dummy_arg=None):
        assert dummy_arg is not None
        x = self.module(input_ids=input_ids, attention_mask=attention_mask,\
                decoder_input_ids=decoder_input_ids, decoder_attention_mask=decoder_attention_mask, lm_labels=lm_labels)
        return x