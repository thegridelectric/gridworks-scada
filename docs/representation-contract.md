# GridWorks Representation Contract

UNDER CONSTRUCTION


The Representation Contract between the Scada and the Ltn is also a contract between the owner of the heating system and the Aggregator.  

At some point, entering the representation contract will involve a smart contract, and the owner of the heating system providing a blockchain TradingRights NFT (non fungible token) to the aggregator, in return for a commitment from the aggregator for a level of service regarding space heating and a commitment regarding money.

The representation contract is a long-standing contract that would only be fully complete if, for example, the homeowner chose to revoke the TradingRights and give them to a different aggregator. It is also an "umbrella agreement" that covers the short-term market-based Dispatch Contracts between the SCADA and the Ltn.

## Brainstorming

There are times when the Scada should decide to break the current Dispatch Contract and not enter into further Dispatch Contracts until there is some non-automated dispute resolution. 

**Question 1** what do we call the above? How do we articulate by messages and in dashboards that the the SCADA through a flag and no further Dispatch Contracts will be entered until this is resolved? Is this a state machine for the Representation Contract? We don't want to call this **breaking the contract** for a variety of reasons: 
   - The SCADA is taking the action but indeed the Ltn is the one violating the terms 
   - The existing DispatchContract may get broken, but there is more than that: further DispatchContracts will not be entered
   - The responsibility for the house getting cold, and any money lost by the system performing sub-optimally while in LocalControl, does need to be clearly articulated and assigned. But an event like this does not mean the home owner is revoking the TradingRights - which is what breaking the Representation Contract sounds like to me. 

For now: SCADA suspends Representation

**Proposal** A human supervisor should be able to both tell the Ltn to stop sending contracts, and the SCADA to stop listening to Ltn contracts. This redundancy ensures that we don’t rely on a single option to put SCADAs in LocalControl. As usual, the human supervisor can also choose to put the SCADA in Admin mode.

**Question 2** Do we want to create roles for two different types of supervisors: one representing the interests of the homeowner/SCADA and one representing the interest of the aggregator? 

Who the human supervisor is and how that person can communicate to the SCADA is not clear yet (at least to me). Do we want someone working as the aggregator to be able to do that? How does that scale if we have an Ltn bug that causes 100 homes to get cold and break contracts with the Ltn? Do we want to have an Ltn message that we could send to a selected group of SCADAs?


**Implementation of first example of this** 
As we discussed yesterday, the SCADA should decide to suspend representation if a critical zone is at least 2 degF below setpoint. Critical zones are selected by the homeowner when the system is installed, and they can update their choice at any time in the app. 

One choice for suspending representaiton: If a critical zone gets 2 degF below setpoint.

Arguably it is an over-reaction to suspend Representaiton only on the basis of the above. Adjustments to consider:
  - We don’t take that decision if a zone gets cold during the last minutes of a contract, we can wait for the next contract and see if it decides to turn on the HP or not
  - We could give a second chance to the Ltn once the zones are all back at setpoint, and if zones get cold again then we decide to break the current contract and all future contracts until a human supervisor intervenes


